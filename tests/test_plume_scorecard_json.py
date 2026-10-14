"""``scripts/plume_eval.py --score-only`` writes the JSON scorecard the Wall's Track record and
``docs/EVALS.md`` cite (``docs/evals/plume-scorecard.json``), beside its Markdown scorecard.

The path comes from the script's ``ROOT`` (``evals/plume`` -> ``docs/evals``), so moving
``ROOT`` to a temporary tree moves the JSON with it and nothing here writes into the repo.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from tephra.config import PROJECT_ROOT


def _load_plume_eval() -> Any:
    spec = importlib.util.spec_from_file_location(
        "tephra_script_plume_eval_json", PROJECT_ROOT / "scripts" / "plume_eval.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


plume_eval = _load_plume_eval()

CASES = {**{f"ash{n}": "ash" for n in range(1, 6)}, **{f"quiet{n}": "quiet" for n in range(1, 6)}}


@pytest.fixture
def eval_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "evals" / "plume"
    monkeypatch.setattr(plume_eval, "ROOT", root)
    monkeypatch.setattr(plume_eval, "CASES_DIR", root / "cases")
    monkeypatch.setattr(plume_eval, "ARM_T_DIR", root / "arm_t")
    monkeypatch.setattr(plume_eval, "RAW_DIR", root / "results" / "raw")
    for case_id, label in CASES.items():
        case_dir = root / "cases" / case_id
        case_dir.mkdir(parents=True)
        case = {
            "id": case_id,
            "class": label,
            "vent_px": [50, 50],
            "image_size": [100, 100],
            "wind_text": "WIND FL180 060/9KT",
        }
        (case_dir / "case.json").write_text(json.dumps(case))
    return root


def _answer(finding: str) -> dict[str, Any]:
    return {
        "image_finding": finding,
        "frames_with_feature": [],
        "plume_box_2d": [],
        "drift_direction": "none",
        "top_fl": None,
        "top_fl_basis": "none",
        "horizon_h": 0,
        "confidence": "medium",
        "confidence_reason": "test",
        "sources": [{"id": "IMG-3", "used_for": "existence"}],
        "disagreements": [],
    }


def _write_runs(root: Path, case_id: str, answers: list[dict[str, Any]]) -> None:
    raw = root / "results" / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for run, answer in enumerate(answers, start=1):
        (raw / f"I_{case_id}_run{run}.json").write_text(json.dumps(answer))


def test_the_json_path_follows_root(eval_root: Path, tmp_path: Path) -> None:
    assert plume_eval.scorecard_json_path() == tmp_path / "docs" / "evals" / "plume-scorecard.json"


def test_score_only_writes_the_json_scorecard(eval_root: Path, tmp_path: Path) -> None:
    """Six of ten cases answered three times: the JSON carries the counts, the verdict words
    and an INCOMPLETE entry that names what is missing; Arm T, without its inputs, is not run."""
    for case_id in sorted(CASES)[:6]:
        label = CASES[case_id]
        _write_runs(
            eval_root, case_id, [_answer("ash_seen" if label == "ash" else "no_ash_seen")] * 3
        )

    assert plume_eval.main(["--score-only", "--model", "test-model"]) == 0

    scorecard = json.loads((tmp_path / "docs" / "evals" / "plume-scorecard.json").read_text())
    assert scorecard["model"] == "test-model"
    assert scorecard["runs"] == 3
    assert scorecard["generated_at"].endswith("Z")
    arm_i = scorecard["arm_i"]
    assert len(arm_i["cases"]) == 10
    assert arm_i["schema"] == {"clean": 18, "expected": 30}
    assert arm_i["existence"] == {"correct": 6, "cases": 10, "quiet_high_confidence_ash": 0}
    assert arm_i["stability"] == {"agreeing": 6, "cases": 10}
    assert arm_i["direction"] == {"detected_within_45_deg": 0}
    assert set(arm_i["verdicts"]) == {"schema", "existence", "direction", "stability"}
    assert all(value.startswith("INCOMPLETE") for value in arm_i["verdicts"].values())
    assert scorecard["arm_t"] is None
    assert scorecard["incomplete"] == [
        "Arm I: 12 of 30 responses not run yet",
        "Arm T: not run",
    ]
    not_run = next(case for case in arm_i["cases"] if case["id"] == "quiet5")
    assert not_run["call"] == "not run"
    assert not_run["runs"] == 0


def test_a_finished_arm_i_has_no_incomplete_entry_for_it(eval_root: Path, tmp_path: Path) -> None:
    for case_id, label in CASES.items():
        _write_runs(
            eval_root, case_id, [_answer("ash_seen" if label == "ash" else "no_ash_seen")] * 3
        )

    assert plume_eval.main(["--arm", "I", "--score-only"]) == 0

    scorecard = json.loads((tmp_path / "docs" / "evals" / "plume-scorecard.json").read_text())
    assert scorecard["arm_i"]["missing"] == 0
    assert scorecard["arm_i"]["verdicts"]["existence"] == "PASS"
    assert scorecard["arm_i"]["verdicts"]["direction"] == "FAIL"
    assert scorecard["incomplete"] == ["Arm T: not run"]


def test_no_inputs_writes_no_json(eval_root: Path, tmp_path: Path) -> None:
    for case_dir in (eval_root / "cases").iterdir():
        (case_dir / "case.json").unlink()
    assert plume_eval.main(["--score-only"]) != 0
    assert not (tmp_path / "docs" / "evals" / "plume-scorecard.json").exists()
