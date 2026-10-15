"""The two GitHub Actions workflows: ci.yml runs on push and pull request with every action
pinned (or tagged with the owner's note until the SHA is looked up), and deploy.yml keeps its
candidate-then-promote gate, its demo environment and a paths filter that covers every
Dockerfile COPY source."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from tephra.config import PROJECT_ROOT

yaml = pytest.importorskip("yaml")

WORKFLOWS = PROJECT_ROOT / ".github" / "workflows"
CI_FILE = WORKFLOWS / "ci.yml"
DEPLOY_FILE = WORKFLOWS / "deploy.yml"
OWNER_NOTE = "owner: replace with the commit SHA"
SHA = re.compile(r"@[0-9a-f]{40}\b")
TAG = re.compile(r"@v\d+(\.\d+)*\b")


def _load(path: Path) -> dict[str, Any]:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    workflow["on"] = workflow.get("on", workflow.get(True))  # YAML 1.1 reads a bare `on` as true
    return workflow


def _uses_lines(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("- uses:", "uses:"))
    ]


def _steps(workflow: dict[str, Any], job: str) -> list[dict[str, Any]]:
    return workflow["jobs"][job]["steps"]


def _runs(workflow: dict[str, Any], job: str) -> list[str]:
    return [str(step["run"]) for step in _steps(workflow, job) if "run" in step]


def test_ci_runs_on_push_to_main_and_on_pull_requests() -> None:
    on = _load(CI_FILE)["on"]
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" in on
    assert "workflow_dispatch" in on


def test_ci_cancels_a_superseded_run_of_the_same_ref() -> None:
    concurrency = _load(CI_FILE)["concurrency"]
    assert concurrency["group"] == "ci-${{ github.ref }}"
    assert concurrency["cancel-in-progress"] is True


@pytest.mark.parametrize("path", [CI_FILE, DEPLOY_FILE])
def test_every_action_is_pinned_to_a_sha_or_carries_the_owner_note(path: Path) -> None:
    lines = _uses_lines(path)
    assert lines
    unpinned = [line for line in lines if not SHA.search(line) and OWNER_NOTE not in line]
    assert unpinned == []
    # A tag is tolerated only on a line that says the owner replaces it.
    for line in lines:
        if TAG.search(line) and not SHA.search(line):
            assert OWNER_NOTE in line


def test_ci_checkout_is_the_sha_deploy_already_uses() -> None:
    deploy_checkout = next(line for line in _uses_lines(DEPLOY_FILE) if "actions/checkout" in line)
    ci_checkout = next(line for line in _uses_lines(CI_FILE) if "actions/checkout" in line)
    ci_sha, deploy_sha = SHA.search(ci_checkout), SHA.search(deploy_checkout)
    assert ci_sha is not None
    assert deploy_sha is not None
    assert ci_sha.group(0) == deploy_sha.group(0)


def test_ci_runs_the_offline_suite_with_a_junit_report_and_no_setup_node() -> None:
    workflow = _load(CI_FILE)
    assert workflow["jobs"]["test"]["env"]["TEPHRA_LLM"] == "stub"
    assert workflow["jobs"]["test"]["timeout-minutes"] == 25
    runs = _runs(workflow, "test")
    assert "uv sync --extra dev" in runs
    assert "uv run ruff check ." in runs
    assert "uv run ruff format --check ." in runs
    assert "node --version" in runs
    pytest_run = next(run for run in runs if "pytest" in run)
    assert pytest_run.startswith("TEPHRA_LLM=stub uv run pytest")
    assert "--junitxml=junit.xml" in pytest_run
    assert "-x" in pytest_run.split()
    assert not any("setup-node" in line for line in _uses_lines(CI_FILE))
    steps = _steps(workflow, "test")
    upload = next(step for step in steps if "upload-artifact" in step.get("uses", ""))
    assert upload["if"] == "always()"
    assert upload["with"]["path"] == "junit.xml"


def test_deploy_does_not_wait_for_the_tests_yet() -> None:
    """A flaky test must not block a fix while two people push (added after 17 Oct 2026)."""
    deploy = _load(DEPLOY_FILE)
    assert "needs" not in deploy["jobs"]["deploy"]
    inputs = deploy["on"]["workflow_dispatch"]["inputs"]
    assert inputs["skip_tests"]["type"] == "boolean"
    assert inputs["skip_tests"]["default"] is False


def test_deploy_keeps_the_candidate_then_promote_gate() -> None:
    deploy = _load(DEPLOY_FILE)
    assert deploy["on"]["push"]["branches"] == ["main"]
    assert deploy["concurrency"]["cancel-in-progress"] is False
    assert "./deploy/cloudrun.sh" in _runs(deploy, "deploy")
    script = (PROJECT_ROOT / "deploy" / "cloudrun.sh").read_text(encoding="utf-8")
    assert "--no-traffic --tag candidate" in script
    assert 'update-traffic "$SERVICE" --region "$REGION" --to-revisions "$CANDIDATE=100"' in script


def test_deploy_env_is_the_demo_configuration() -> None:
    env = _load(DEPLOY_FILE)["env"]
    assert env["TEPHRA_MODE"] == "REPLAY"
    assert env["TEPHRA_REPLAY_CASE"] == "anak-krakatau-20260905"
    assert env["TEPHRA_FEATURES"] == "connect"
    assert env["TEPHRA_VISITOR_ACCESS"] == "replay"
    assert env["TEPHRA_REPLAY_QUANTUM_S"] == "60"
    assert env["TEPHRA_RECOVERY_AUTO"] == "false"
    assert env["TEPHRA_CLOUD_REGION"] == "asia-southeast1"
    # Held back until the answer store has filled (push 4); the line is there to uncomment.
    assert "TEPHRA_AI_INTERACTIVE_SHARE" not in env
    assert '# TEPHRA_AI_INTERACTIVE_SHARE: "0.3"' in DEPLOY_FILE.read_text(encoding="utf-8")


def test_deploy_paths_cover_every_dockerfile_copy_source() -> None:
    patterns: list[str] = _load(DEPLOY_FILE)["on"]["push"]["paths"]
    sources: list[str] = []
    for line in (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines():
        words = line.split()
        if len(words) < 3 or words[0] != "COPY" or words[1].startswith("--from"):
            continue
        sources += [word for word in words[1:-1] if not word.startswith("--")]
    assert "docs/evals" in sources
    uncovered = []
    for source in sources:
        if source in {"README.md", "LICENSE"}:  # package metadata only; no behaviour
            continue
        covered = any(
            pattern == source or (pattern.endswith("/**") and source == pattern[: -len("/**")])
            for pattern in patterns
        )
        if not covered:
            uncovered.append(source)
    assert uncovered == []


def test_no_workflow_addresses_a_judge() -> None:
    for path in (CI_FILE, DEPLOY_FILE):
        assert not re.search(r"\bjudg", path.read_text(encoding="utf-8"), re.IGNORECASE), path
