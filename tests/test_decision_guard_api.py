"""The decision guard at the API: a HYPOTHESIS draft that advises more than MONITOR or HOLD
is refused with 409 ``rule_blocked``, a draft written for an ash area the server no longer
holds with 409 ``cone_changed``, and each refusal is one trace line on the Wall. The cone the
server compares against is ``cones/<volcano_id>`` in the store, which the pipeline writes on
every change; a draft of the other mode, or a volcano with no cone held, is not compared."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from test_api import ADVISORY_ID, PIN, FakeRuntime, make_advisory

from tephra.api.server import create_app
from tephra.config import Settings
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    PlumeMode,
    RunMode,
    SseEvent,
    TraceEvent,
)
from tephra.pipeline import Runtime
from tephra.store import open_store
from tephra.store.base import Collection

HYPOTHESIS_REFUSAL = "HYPOTHESIS ALLOWS ONLY MONITOR OR HOLD; REJECT THIS DRAFT"
CHANGED_REFUSAL = "THE ASH AREA CHANGED SINCE THIS DRAFT WAS WRITTEN; A NEW PLAN IS DUE"
DRAFT_CONE = "CONE-0123456789ab"


@dataclass
class GuardRuntime(FakeRuntime):
    """The API stand-in plus the trace the refusal writes."""

    traces: list[TraceEvent] = field(default_factory=list)

    def trace(self, stage: Any, actor: Any, message: str, **extra: Any) -> TraceEvent:
        event = TraceEvent.new(stage, actor, message, **extra)
        self.traces.append(event)
        self.bus.publish(SseEvent.TRACE, event)
        return event


class Harness:
    """Seeds one draft (``changes`` on the API test's advisory) and, when given, the cone the
    server holds for its volcano."""

    def __init__(self, *, held_cone: str | None = None, **changes: Any) -> None:
        self.draft = make_advisory().model_copy(update=changes)
        self.held_cone = held_cone
        self._runtime: GuardRuntime | None = None

    @property
    def runtime(self) -> GuardRuntime:
        assert self._runtime is not None, "app not started"
        return self._runtime

    async def factory(self, settings: Settings) -> Runtime:
        store = open_store(settings)
        assert await store.compare_and_set_advisory(
            self.draft.id, 0, self.draft.model_dump(mode="json")
        )
        if self.held_cone is not None:
            await store.put(Collection.CONES, self.draft.volcano_id, {"id": self.held_cone})
        self._runtime = GuardRuntime(settings=settings, store=store)
        return cast(Runtime, self._runtime)


def make_settings(home: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=home / "tephra.sqlite3",
        cache_dir=home / "cache",
        data_dir=home / "data",
        desk_pin=PIN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


@pytest.fixture
def serve(tmp_path: Path) -> Iterator[Any]:
    """``serve(harness)`` -> a logged-in client over that harness, each app on its own store."""
    opened: list[TestClient] = []

    def start(harness: Harness) -> TestClient:
        home = tmp_path / f"app{len(opened)}"
        client = TestClient(create_app(make_settings(home), runtime_factory=harness.factory))
        client.__enter__()
        opened.append(client)
        login = client.post("/api/desk/login", json={"pin": PIN, "name": "Ana K"})
        assert login.status_code == 200
        return client

    yield start
    for client in opened:
        client.__exit__(None, None, None)


def approve(client: TestClient) -> httpx.Response:
    return client.post(f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 1})


def edit(client: TestClient, body: str) -> httpx.Response:
    return client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/edit", json={"version": 1, "body": body}
    )


def still_a_draft(client: TestClient) -> None:
    listed = client.get("/api/advisories").json()["advisories"]
    current = Advisory.model_validate(next(a for a in listed if a["id"] == ADVISORY_ID))
    assert (current.status, current.version) == (AdvisoryStatus.DRAFT, 1)
    actions = [row["action"] for row in client.get("/api/audit").json()["entries"]]
    assert "APPROVED" not in actions
    assert "EDITED" not in actions
    assert client.get("/api/outbound").json()["messages"] == []


def test_a_hypothesis_divert_is_refused_with_rule_blocked(serve: Any) -> None:
    harness = Harness(
        plume_mode=PlumeMode.HYPOTHESIS,
        action=ActionKind.DIVERT,
        alternate_icao="WADD",
        body="DIVERT TO WADD. ASH SFC/FL150 AHEAD, ENTRY 14 MIN. REPORT VAR.",
    )
    client = serve(harness)
    response = approve(client)
    assert response.status_code == 409
    assert response.json() == {
        "error": "rule_blocked",
        "detail": HYPOTHESIS_REFUSAL,
        "problems": [HYPOTHESIS_REFUSAL],
        "current": None,
    }
    edited = edit(client, "MONITOR ASH AHEAD. REPORT VAR.")
    assert edited.status_code == 409
    assert edited.json()["error"] == "rule_blocked"
    still_a_draft(client)
    flight = harness.draft.proxy_flight
    lines = [(e.stage.value, e.actor, e.level, e.message) for e in harness.runtime.traces]
    assert lines == [
        ("DESK", "code", "warn", f"{flight}: approval refused: {HYPOTHESIS_REFUSAL}"),
        ("DESK", "code", "warn", f"{flight}: approval refused: {HYPOTHESIS_REFUSAL}"),
    ]
    assert harness.runtime.traces[0].flight_id == harness.draft.flight_id
    assert [e.data["message"] for e in harness.runtime.bus.recent(SseEvent.TRACE, limit=5)] == [
        line[3] for line in lines
    ]


def test_an_edit_cannot_add_a_divert_under_hypothesis(serve: Any) -> None:
    client = serve(Harness(plume_mode=PlumeMode.HYPOTHESIS, action=ActionKind.HOLD))
    response = edit(client, "DIVERT TO WADD NOW. ASH AHEAD.")
    assert response.status_code == 422
    assert response.json()["error"] == "validation_failed"
    assert any("HYPOTHESIS" in problem for problem in response.json()["problems"])
    still_a_draft(client)


def test_a_draft_for_an_older_ash_area_is_refused_with_cone_changed(serve: Any) -> None:
    harness = Harness(held_cone="CONE-fedcba987654")
    client = serve(harness)
    response = approve(client)
    assert response.status_code == 409
    assert response.json() == {
        "error": "cone_changed",
        "detail": CHANGED_REFUSAL,
        "problems": [CHANGED_REFUSAL],
        "current": None,
    }
    assert edit(client, "HOLD PRESENT POSITION FL350. REPORT VAR.").json()["error"] == (
        "cone_changed"
    )
    still_a_draft(client)
    assert [e.message for e in harness.runtime.traces] == [
        f"{harness.draft.proxy_flight}: approval refused: {CHANGED_REFUSAL}"
    ] * 2
    # the reject stays open
    rejected = client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/reject",
        json={"version": 1, "reason": "situation moved on"},
    )
    assert rejected.status_code == 200


def test_the_cone_held_now_passes_and_no_cone_held_is_not_compared(serve: Any) -> None:
    same = serve(Harness(held_cone=DRAFT_CONE))
    assert approve(same).status_code == 200
    none_held = serve(Harness())
    assert approve(none_held).status_code == 200


def test_a_draft_of_the_other_mode_is_not_compared(serve: Any) -> None:
    """A REPLAY draft while LIVE plays: the cone held belongs to the other picture."""
    harness = Harness(held_cone="CONE-fedcba987654", replay=True)
    client = serve(harness)
    assert harness.runtime.mode is RunMode.LIVE
    assert approve(client).status_code == 200
    assert harness.runtime.traces == []


def test_a_hypothesis_hold_is_approved(serve: Any) -> None:
    client = serve(Harness(plume_mode=PlumeMode.HYPOTHESIS, action=ActionKind.HOLD))
    response = approve(client)
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"
