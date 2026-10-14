"""``scripts/prewarm_replay.py``: the fill loop, its refusals, and the export a REPLAY run
loads as the case's seed. Offline: the stub backend through the counting stand-in."""

import argparse
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType

import pytest

from tephra.agents.answers import AiAnswer
from tephra.config import PROJECT_ROOT
from tephra.models import RunMode
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"tephra_script_{name}", PROJECT_ROOT / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prewarm = _load("prewarm_replay")

START = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def stand_ins_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    """The counting stand-ins replace two module attributes; put them back after the test."""
    from tephra.agents import duty_officer, exposure_planner

    for module in (exposure_planner, duty_officer):
        monkeypatch.setattr(module, "_run_agent", module._run_agent)
    monkeypatch.setenv("TEPHRA_LLM", "stub")


def _argv(tmp_path: Path, *extra: str) -> list[str]:
    return [
        "--case",
        "anak-krakatau-20260905",
        "--start",
        "2026-09-05T12:00:00Z",
        "--minutes",
        "3",
        "--loops",
        "1",
        "--quantum-s",
        "60",
        "--store",
        str(tmp_path / "prewarm.sqlite3"),
        *extra,
    ]


def test_the_fill_refuses_to_start_unless_the_service_budget_is_paused(
    tmp_path: Path, stand_ins_restored: None, capsys: pytest.CaptureFixture[str]
) -> None:
    assert prewarm.main(_argv(tmp_path)) == prewarm.EXIT_REFUSED
    assert "service-budget-paused" in capsys.readouterr().err
    assert not (tmp_path / "prewarm.sqlite3").exists()


def test_stub_answers_are_never_exported_without_the_flag(
    tmp_path: Path, stand_ins_restored: None
) -> None:
    argv = _argv(tmp_path, "--service-budget-paused", "--export", str(tmp_path / "answers"))
    with pytest.raises(SystemExit, match="stub answers"):
        prewarm.main(argv)
    assert not (tmp_path / "answers" / "ai_answers.jsonl").exists()


def test_a_stub_dry_run_writes_a_jsonl_the_loader_reads_back(
    tmp_path: Path, stand_ins_restored: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Three replay minutes with the counting stand-in keep answers in the fill store; the
    export holds each as stored, and a fresh store reads every line back under its key."""
    out = tmp_path / "answers"
    argv = _argv(tmp_path, "--service-budget-paused", "--export", str(out), "--allow-stub-export")

    assert prewarm.main(argv) == 0

    printed = capsys.readouterr().out
    assert '"status": "filled"' in printed
    lines = (out / "ai_answers.jsonl").read_text().splitlines()
    assert lines
    answers = [AiAnswer.model_validate_json(line) for line in lines]
    assert {answer.mode for answer in answers} == {RunMode.REPLAY}
    assert {answer.case_id for answer in answers} == {"anak-krakatau-20260905"}
    assert {answer.skill for answer in answers} >= {"flight_planner", "drafter"}
    summary = json.loads((out / "answers.json").read_text())
    assert summary["case_id"] == "anak-krakatau-20260905"
    assert summary["counts"] == {
        skill: sum(1 for answer in answers if answer.skill == skill)
        for skill in sorted({answer.skill for answer in answers})
    }
    assert summary["recorded_wall_from"] <= summary["recorded_wall_to"]
    assert set(summary["models"]) == {"main", "lite"}
    assert "plume_reader" in summary["prompt_versions"]
    assert all(len(version) == 16 for version in summary["prompt_versions"].values())
    assert summary["model_ids"] == sorted({answer.model_id for answer in answers})

    async def read_back() -> None:
        store = SqliteStore(tmp_path / "fresh.sqlite3", tmp_path / "fresh-blobs")
        try:
            for line in lines:
                doc = json.loads(line)
                await store.put(Collection.AI_ANSWERS, doc["key"], doc)
            for answer in answers:
                stored = await store.get(Collection.AI_ANSWERS, answer.key)
                assert stored is not None
                assert AiAnswer.model_validate(stored) == answer
        finally:
            await store.aclose()

    import asyncio

    asyncio.run(read_back())


def test_the_export_only_path_needs_a_directory() -> None:
    with pytest.raises(SystemExit):
        prewarm.parse_args(["--export-from-store", "firestore"])
    args = prewarm.parse_args(["--export-from-store", "firestore", "--export", "x"])
    assert args.store == "firestore"
    assert isinstance(args, argparse.Namespace)


def test_a_stub_answer_is_recognised_by_its_model_id() -> None:
    assert prewarm.is_stub_answer({"model_id": "stub"})
    assert prewarm.is_stub_answer({"model_id": "counting-lite"})
    assert prewarm.is_stub_answer({"model_id": "gemini-x", "llm_backend": "stub"})
    assert not prewarm.is_stub_answer({"model_id": "gemini-3.8-flash-lite"})
