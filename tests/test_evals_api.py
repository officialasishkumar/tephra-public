"""``GET /api/evals``: the committed ``docs/evals/*.json`` scorecards, cached for five minutes;
404 when the folder holds none. Until the server mounts ``routes_evals`` the test mounts it."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tephra.api import routes_evals
from tephra.api.server import create_app
from tephra.config import PROJECT_ROOT, Settings
from tephra.models import OperatorPolicy, PolicySummary, RunMode, TickReport
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.store import open_store
from tephra.store.base import Store
from tephra.util import timeutil
from tephra.util.events import EventBus

POLICY = load_policy(PROJECT_ROOT / "data")
EVALS_DIR = PROJECT_ROOT / "docs" / "evals"


@dataclass
class FakeRuntime:
    """The parts of ``tephra.pipeline.Runtime`` the lifespan touches."""

    settings: Settings
    store: Store
    bus: EventBus = field(default_factory=EventBus)
    mode: RunMode = RunMode.LIVE
    policy: OperatorPolicy = field(default_factory=lambda: POLICY)
    policy_summary: PolicySummary = field(default_factory=lambda: PolicySummary.of(POLICY))

    async def tick(self, *, reason: str = "scheduler") -> TickReport:
        at = timeutil.now()
        return TickReport(started_at=at, finished_at=at, mode=self.mode, reason=reason)

    async def aclose(self) -> None:
        await self.store.aclose()


async def factory(settings: Settings) -> Runtime:
    return cast(Runtime, FakeRuntime(settings=settings, store=open_store(settings)))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin="zulu-4711",
        task_token="task-token-for-tests-0123456789abcdef",
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


def mount_evals(app: FastAPI) -> None:
    paths = {getattr(route, "path", None) for route in app.routes}
    if "/api/evals" not in paths:
        app.include_router(routes_evals.router, prefix="/api")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, runtime_factory=factory)
    mount_evals(app)
    with TestClient(app) as test_client:
        yield test_client


def test_evals_serves_the_committed_scorecards(client: TestClient) -> None:
    response = client.get("/api/evals")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert set(body) == {"plume", "replay_metrics", "call_counts"}
    for key, name in routes_evals.EVAL_FILES.items():
        path = EVALS_DIR / name
        if path.is_file():
            assert body[key] == json.loads(path.read_text(encoding="utf-8")), name
        else:
            assert body[key] is None, name
    # The committed plume scorecard is the one scripts/plume_eval.py --score-only wrote.
    assert body["plume"] is not None
    assert "arm_i" in body["plume"]


def test_evals_is_404_with_no_files(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "evals"
    empty.mkdir()
    monkeypatch.setattr(routes_evals, "EVALS_DIR", empty)
    app = create_app(settings, runtime_factory=factory)
    mount_evals(app)
    with TestClient(app) as client:
        response = client.get("/api/evals")
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"
        assert response.headers["cache-control"] == "no-store"


def test_a_broken_scorecard_is_503_not_a_half_read_bundle(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "evals"
    folder.mkdir()
    (folder / "plume-scorecard.json").write_text('{"runs": 3}', encoding="utf-8")
    (folder / "call-counts.json").write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setattr(routes_evals, "EVALS_DIR", folder)
    app = create_app(settings, runtime_factory=factory)
    mount_evals(app)
    with TestClient(app) as client:
        response = client.get("/api/evals")
        assert response.status_code == 503
        assert response.json()["error"] == "unavailable"
