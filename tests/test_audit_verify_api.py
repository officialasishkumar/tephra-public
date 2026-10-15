"""``GET /api/audit/verify``: the audit chain's head as this instance last verified it,
public, count and hash only; 503 ``starting`` before a head exists; ``/api/audit`` carries
each entry's place in the chain."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from test_api import PIN, FakeRuntime

from tephra.api.server import AUDIT_VERIFY_NOTE, create_app
from tephra.config import Settings
from tephra.models import ChainHead
from tephra.pipeline import Runtime
from tephra.store import open_store

CHECKED_AT = datetime(2026, 10, 15, 9, 30, tzinfo=UTC)


@dataclass
class ChainRuntime(FakeRuntime):
    audit_head: ChainHead | None = None


class Harness:
    def __init__(self) -> None:
        self._runtime: ChainRuntime | None = None

    @property
    def runtime(self) -> ChainRuntime:
        assert self._runtime is not None, "app not started"
        return self._runtime

    async def factory(self, settings: Settings) -> Runtime:
        self._runtime = ChainRuntime(settings=settings, store=open_store(settings))
        return cast(Runtime, self._runtime)


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(tmp_path: Path, harness: Harness) -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )
    with TestClient(create_app(settings, runtime_factory=harness.factory)) as test_client:
        yield test_client


def head(**changes: object) -> ChainHead:
    base = ChainHead(seq=1204, sha256="f" * 64, checked_at=CHECKED_AT, entries=1204, intact=True)
    return base.model_copy(update=changes)


def test_verify_is_503_before_the_chain_has_been_checked(client: TestClient) -> None:
    response = client.get("/api/audit/verify")
    assert response.status_code == 503
    assert response.json()["error"] == "starting"


def test_verify_has_the_shape_of_the_head(client: TestClient, harness: Harness) -> None:
    harness.runtime.audit_head = head()
    response = client.get("/api/audit/verify")
    assert response.status_code == 200
    assert response.json() == {
        "intact": True,
        "entries": 1204,
        "head_seq": 1204,
        "head_sha256": "f" * 64,
        "checked_at": "2026-10-15T09:30:00.000Z",
        "problems": [],
        "note": AUDIT_VERIFY_NOTE,
    }
    assert AUDIT_VERIFY_NOTE == (
        "walked from the first entry at startup; later entries are linked as written"
    )
    assert response.headers["cache-control"] == "no-store"


def test_verify_is_public_and_lists_the_first_five_problems(
    client: TestClient, harness: Harness
) -> None:
    problems = [f"broken link at seq {n}" for n in range(1, 8)]
    harness.runtime.audit_head = head(intact=False, problems=problems)
    body = client.get("/api/audit/verify").json()
    assert body["intact"] is False
    assert body["problems"] == problems[:5]
    assert "tephra_desk" not in client.cookies


def test_the_audit_list_carries_the_chain_fields(client: TestClient) -> None:
    assert client.post("/api/desk/login", json={"pin": PIN, "name": "Ana K"}).status_code == 200
    entries = client.get("/api/audit").json()["entries"]
    assert [row["action"] for row in entries] == ["LOGIN_OK"]
    row = entries[0]
    assert row["seq"] == 1
    assert row["prev_sha256"] == "0" * 64
    assert len(row["sha256"]) == 64
