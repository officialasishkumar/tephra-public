"""The Operator policy dialog's logic (``tephra/web/wall/policy.js``, docs/UI-DESIGN.md 7.18).

Every value of ``data/policy/policy_a.json`` must be reachable in the dialog exactly once, under a
name a person reads, with its number and unit written out; the reasons are the file's own words,
only split for display (a semicolon becomes a full stop, the "TEPHRA illustrative choice" opening
becomes a tag). Runs the module under Node; skipped when Node is not installed.
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
WALL = ROOT / "tephra" / "web" / "wall"
POLICY = json.loads((ROOT / "data" / "policy" / "policy_a.json").read_text(encoding="utf-8"))
NODE = shutil.which("node")

RUNNER = """
import { readFileSync } from "node:fs";
import { policyValues, formatValue, reasonParts } from "./wall/policy.js";
const policy = JSON.parse(readFileSync(process.argv[2], "utf8"));
const groups = policyValues(policy);
const reasons = groups.flatMap((g) => g.rows.map((r) => [r.id, reasonParts(r.raw.source)]));
const pairs = JSON.parse(process.argv[3]);
const samples = Object.fromEntries(pairs.map(([k, v]) => [k, formatValue(k, v)]));
const summary = reasonParts(policy.summary_text);
process.stdout.write(JSON.stringify({ groups, reasons, samples, summary }));
"""

pytestmark = pytest.mark.skipif(NODE is None, reason="Node is not installed")


def _letters(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalnum())


def _value_ids(policy: dict[str, Any]) -> list[str]:
    return [
        f"{block}.{name}"
        for block, body in policy.items()
        if isinstance(body, dict)
        for name, value in body.items()
        if isinstance(value, dict) and {"value", "unit"} <= value.keys()
    ]


@pytest.fixture(scope="module")
def dialog(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    tmp = tmp_path_factory.mktemp("policy")
    (tmp / "wall").mkdir()
    for name in ("policy.js", "util.js", "dk.js", "x-parts.js"):
        shutil.copy(WALL / name, tmp / "wall" / name)
    (tmp / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    (tmp / "run.mjs").write_text(RUNNER, encoding="utf-8")
    (tmp / "policy.json").write_text(json.dumps(POLICY), encoding="utf-8")
    samples = [
        ["vertical_margin_ft", {"value": 2000, "unit": "ft"}],
        ["max_change_level_fl", {"value": 410, "unit": "FL"}],
        ["level_band_fl", {"value": 20, "unit": "FL"}],
        ["max_delay_min", {"value": 360, "unit": "min"}],
        ["divert_within_min", {"value": 15, "unit": "min"}],
        ["cancel_cost_fixed_usd", {"value": 1500, "unit": "USD"}],
        ["max_turn_deg", {"value": 90, "unit": "deg"}],
        ["max_waypoints_count", {"value": 4, "unit": "count"}],
    ]
    result = subprocess.run(
        [str(NODE), "run.mjs", "policy.json", json.dumps(samples)],
        cwd=tmp,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(result.stdout)


def test_every_value_of_the_file_is_shown_once(dialog: dict[str, Any]) -> None:
    shown = [row["id"] for group in dialog["groups"] for row in group["rows"]]
    assert sorted(shown) == sorted(_value_ids(POLICY))
    assert len(shown) == len(set(shown))


def test_every_value_has_a_name_a_person_reads(dialog: dict[str, Any]) -> None:
    for group in dialog["groups"]:
        assert group["about"], group["key"]
        for row in group["rows"]:
            # a label made from the setting's own words would mean a missing entry in LABELS
            assert "_" not in row["label"], row["id"]
            assert row["label"] != row["id"], row["id"]


def test_numbers_and_units_are_written_out(dialog: dict[str, Any]) -> None:
    nb = chr(0xA0)  # a no-break space: a number and its unit never wrap apart
    assert dialog["samples"] == {
        "vertical_margin_ft": f"2,000{nb}ft",
        "max_change_level_fl": "FL410",
        "level_band_fl": f"20{nb}FL (2,000{nb}ft)",
        "max_delay_min": f"360{nb}min (6{nb}h)",
        "divert_within_min": f"15{nb}min",
        "cancel_cost_fixed_usd": "$1,500",
        "max_turn_deg": "90°",
        "max_waypoints_count": "4",
    }


def test_reasons_keep_their_words_without_semicolons(dialog: dict[str, Any]) -> None:
    sources = {
        f"{block}.{name}": value["source"]
        for block, body in POLICY.items()
        if isinstance(body, dict)
        for name, value in body.items()
        if isinstance(value, dict) and "source" in value
    }
    for value_id, parts in dialog["reasons"]:
        assert ";" not in parts["text"], value_id
        original = sources[value_id]
        if original.startswith("TEPHRA illustrative choice"):
            assert parts["tag"].startswith("Illustrative choice"), value_id
        # the same words, in the same order, apart from the opening and the punctuation
        assert _letters(original).endswith(_letters(parts["text"])), value_id
    assert ";" not in dialog["summary"]["text"]
