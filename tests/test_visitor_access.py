"""The visitor role over HTTP: minted without a PIN while a replay plays, audited as
``visitor:<name>``, refused where only a dispatcher may change the server's picture, capped
per session, and never a decision-maker in LIVE. A dispatcher's session is unchanged, and a
cookie minted before roles existed still verifies as a dispatcher.

The stand-in runtime is ``tests/test_api.py``'s with what Ask TEPHRA and the chain reads
added; the draft it seeds is a REPLAY draft so the cone check runs on a visitor's approval.
"""

import base64
import hashlib
import hmac
import json
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from test_api import ADVISORY_ID, DISPATCHER, PIN, FakeRuntime, make_advisory

from tephra.agents.llm import StubBackend
from tephra.api.auth import (
    DISPATCHER_ONLY_PATHS,
    VISITOR_ASK_PATHS,
    VISITOR_DECISION_PATHS,
    sign_session,
    verify_session,
)
from tephra.api.server import VISITOR_MINTS_PER_WINDOW, create_app
from tephra.config import Settings
from tephra.feeds.registry import LiveData
from tephra.models import (
    AuditAction,
    ChainHead,
    RunMode,
    SseEvent,
    SystemState,
    TraceEvent,
)
from tephra.pipeline import Runtime
from tephra.store import open_store
from tephra.store.base import Collection

SECRET = "test-session-secret-0123456789abcdef"
VISITOR = "Mira"
CONE_ID = "CONE-0123456789ab"


@dataclass
class VisitorRuntime(FakeRuntime):
    """The API stand-in plus what Ask TEPHRA's stub reads and what the chain route shows."""

    llm: Any = field(default_factory=StubBackend)
    live: LiveData = field(default_factory=LiveData)
    situations: dict[str, Any] = field(default_factory=dict)
    assessments: dict[str, Any] = field(default_factory=dict)
    cones: dict[str, Any] = field(default_factory=dict)
    exposed: dict[str, Any] = field(default_factory=dict)
    answers: Any = None
    duty: Any = None
    audit_head: ChainHead | None = None

    def aircraft(self) -> list[Any]:
        return []

    def trace(self, stage: Any, actor: Any, message: str, **extra: Any) -> TraceEvent:
        event = TraceEvent.new(stage, actor, message, **extra)
        self.bus.publish(SseEvent.TRACE, event)
        return event

    async def publish_budget(self) -> None:
        return None

    async def system_state(self) -> SystemState:
        state = await super().system_state()
        on = self.settings.visitor_access == "replay" and self.mode is RunMode.REPLAY
        return state.model_copy(update={"visitor_access": on})


class Harness:
    def __init__(self, *, mode: RunMode = RunMode.REPLAY) -> None:
        self.mode = mode
        self._runtime: VisitorRuntime | None = None

    @property
    def runtime(self) -> VisitorRuntime:
        assert self._runtime is not None, "app not started"
        return self._runtime

    async def factory(self, settings: Settings) -> Runtime:
        store = open_store(settings)
        draft = make_advisory().model_copy(update={"replay": self.mode is RunMode.REPLAY})
        assert await store.compare_and_set_advisory(ADVISORY_ID, 0, draft.model_dump(mode="json"))
        await store.put(Collection.CONES, draft.volcano_id, {"id": CONE_ID})
        self._runtime = VisitorRuntime(settings=settings, store=store, mode=self.mode)
        return cast(Runtime, self._runtime)


def make_settings(tmp_path: Path, **changes: Any) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        session_secret=SECRET,
        local_scheduler=False,
        **{"visitor_access": "replay", **changes},
    )


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(tmp_path: Path, harness: Harness) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path), runtime_factory=harness.factory)
    with TestClient(app) as test_client:
        yield test_client


def enter(client: TestClient, name: str | None = VISITOR) -> httpx.Response:
    return client.post("/api/desk/visitor", json={"name": name})


def login(client: TestClient, *, pin: str = PIN, name: str = DISPATCHER) -> httpx.Response:
    return client.post("/api/desk/login", json={"pin": pin, "name": name})


def approve(client: TestClient, advisory_id: str = ADVISORY_ID, version: int = 1) -> httpx.Response:
    return client.post(f"/api/desk/advisories/{advisory_id}/approve", json={"version": version})


def reject(client: TestClient, advisory_id: str = ADVISORY_ID) -> httpx.Response:
    return client.post(
        f"/api/desk/advisories/{advisory_id}/reject",
        json={"version": 1, "reason": "not needed for this test"},
    )


def audit_rows(client: TestClient) -> list[dict[str, Any]]:
    return list(client.get("/api/audit").json()["entries"])


def forge_token(claims: dict[str, Any]) -> str:
    """A token built the way auth documents it, by someone who holds the secret."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=")
    mac = hmac.new(SECRET.encode(), payload, hashlib.sha256).digest()
    return f"{payload.decode()}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"


# --- minting ------------------------------------------------------------------------------


def test_a_visitor_is_minted_with_its_role_and_audited(client: TestClient) -> None:
    response = enter(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["name"], body["role"]) == (VISITOR, "visitor")
    assert isinstance(body["sid"], str)
    assert len(body["sid"]) == 16
    assert "tephra_desk" in response.cookies
    me = client.get("/api/desk/me").json()
    assert (me["name"], me["role"], me["sid"]) == (VISITOR, "visitor", body["sid"])
    entered = [row for row in audit_rows(client) if row["action"] == "VISITOR_ENTERED"]
    assert [row["actor"] for row in entered] == [f"visitor:{VISITOR}"]
    assert entered[0]["seq"] is not None
    assert len(entered[0]["sha256"]) == 64


def test_a_nameless_visitor_gets_a_visitor_name(client: TestClient) -> None:
    body = enter(client, None).json()
    assert body["name"].startswith("Visitor-")
    assert len(body["name"]) == len("Visitor-abcd")
    assert client.post("/api/desk/visitor", json={}).json()["name"].startswith("Visitor-")


def test_a_bad_visitor_name_is_refused_like_a_dispatchers(client: TestClient) -> None:
    assert enter(client, "x").status_code == 422
    assert enter(client, "<script>").status_code == 422


def test_a_visitor_session_expires_on_the_visitor_ttl(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, visitor_session_ttl_h=2.0, desk_session_ttl_h=12.0)
    at = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    token, expires_at = sign_session(VISITOR, settings, at=at, role="visitor")
    assert (expires_at - at).total_seconds() == 2 * 3600
    assert verify_session(token, settings, at=at) is not None
    assert verify_session(token, settings, at=at.replace(hour=14, second=1)) is None


def test_visitor_access_off_is_503(tmp_path: Path) -> None:
    harness = Harness()
    app = create_app(make_settings(tmp_path, visitor_access="off"), runtime_factory=harness.factory)
    with TestClient(app) as client:
        response = enter(client)
        assert response.status_code == 503
        assert response.json() == {
            "error": "visitor_off",
            "detail": "Visitor access is switched off on this server.",
            "problems": [],
            "current": None,
        }
        assert client.get("/api/state").json()["visitor_access"] is False


def test_live_mints_no_visitor_and_refuses_a_visitors_decision(tmp_path: Path) -> None:
    harness = Harness(mode=RunMode.LIVE)
    app = create_app(make_settings(tmp_path), runtime_factory=harness.factory)
    with TestClient(app) as client:
        assert enter(client).json()["error"] == "visitor_off"
        assert client.get("/api/state").json()["visitor_access"] is False
        harness.runtime.mode = RunMode.REPLAY
        assert enter(client).status_code == 200
        assert client.get("/api/state").json()["visitor_access"] is True
        harness.runtime.mode = RunMode.LIVE
        response = approve(client)
        assert response.status_code == 403
        assert response.json()["error"] == "visitor_replay_only"
        assert response.json()["detail"] == "Visitors can decide only while a replay plays."
        ask = client.post("/api/desk/ask", json={"question": "Which flights?"})
        assert ask.json()["error"] == "visitor_replay_only"
        # reading stays open to the session
        assert client.get("/api/desk/advisories").status_code == 200


def test_too_many_visitors_from_one_address_is_429(client: TestClient) -> None:
    for _ in range(VISITOR_MINTS_PER_WINDOW):
        assert enter(client).status_code == 200
    refused = enter(client)
    assert refused.status_code == 429
    assert refused.json()["error"] == "too_many_visitors"
    assert int(refused.headers["retry-after"]) >= 1


def test_the_visitor_route_needs_the_csrf_proof(client: TestClient) -> None:
    assert client.post("/api/desk/visitor", content=b"", headers={}).status_code == 403


# --- what a visitor may and may not do -----------------------------------------------------


def test_a_visitor_cannot_switch_the_mode(client: TestClient) -> None:
    enter(client)
    response = client.post("/api/mode", json={"mode": "LIVE"})
    assert response.status_code == 403
    assert response.json()["error"] == "visitor_role"
    assert response.json()["detail"] == "Visitors cannot do this; a dispatcher can."


@pytest.mark.parametrize(("method", "path"), DISPATCHER_ONLY_PATHS)
def test_each_dispatcher_only_path_refuses_a_visitor(
    client: TestClient, method: str, path: str
) -> None:
    enter(client)
    response = client.request(method, path, json={})
    assert response.status_code == 403, (path, response.text)
    assert response.json()["error"] == "visitor_role"


def test_a_visitor_approves_a_draft_and_the_audit_names_the_visitor(
    client: TestClient, harness: Harness
) -> None:
    enter(client)
    response = approve(client)
    assert response.status_code == 200, response.text
    assert response.json()["decided_by"] == f"visitor:{VISITOR}"
    approved = [row for row in audit_rows(client) if row["action"] == "APPROVED"]
    assert [row["actor"] for row in approved] == [f"visitor:{VISITOR}"]
    queued = client.get("/api/outbound").json()["messages"]
    assert [item["approved_by"] for item in queued] == [f"visitor:{VISITOR}"]


@pytest.mark.parametrize(("method", "prefix", "suffix"), VISITOR_DECISION_PATHS)
def test_each_decision_path_counts_against_the_visitor_cap(
    client: TestClient, method: str, prefix: str, suffix: str
) -> None:
    sid = enter(client).json()["sid"]
    decisions: Counter[str] = client.app.state.visitor_decisions  # type: ignore[attr-defined]
    assert decisions[sid] == 0
    response = client.request(method, f"{prefix}x_0123456789ab{suffix}", json={})
    assert response.status_code != 403, (prefix, suffix, response.text)
    assert decisions[sid] == 1


def test_the_41st_decision_is_refused(tmp_path: Path) -> None:
    harness = Harness()
    settings = make_settings(tmp_path)
    app = create_app(settings, runtime_factory=harness.factory)
    with TestClient(app) as client:
        sid = enter(client).json()["sid"]
        assert reject(client).status_code == 200
        for _ in range(settings.visitor_decision_cap - 1):
            assert reject(client).status_code == 409  # already decided; still a decision asked
        refused = reject(client)
        assert refused.status_code == 429
        assert refused.json()["error"] == "visitor_cap"
        assert refused.json()["detail"] == (
            "This visitor session has made its 40 decisions. Enter again to continue."
        )
        # a fresh visitor session starts at zero
        again = enter(client).json()["sid"]
        assert again != sid
        assert reject(client).status_code == 409


def test_the_fourth_question_is_refused(client: TestClient) -> None:
    enter(client)
    for _ in range(3):
        response = client.post("/api/desk/ask", json={"question": "Which flights are exposed?"})
        assert response.status_code == 200, response.text
    refused = client.post("/api/desk/ask", json={"question": "And now?"})
    assert refused.status_code == 429
    assert refused.json()["error"] == "visitor_ask_cap"
    assert refused.json()["detail"] == "Visitors may ask three questions a session."


def test_speaking_a_stored_answer_is_not_a_question(client: TestClient) -> None:
    sid = enter(client).json()["sid"]
    decisions: Counter[str] = client.app.state.visitor_decisions  # type: ignore[attr-defined]
    client.post("/api/desk/ask/speak", json={"answer_id": "ask_0123456789ab"})
    assert decisions[f"{sid}:ask"] == 0
    assert ("POST", "/api/desk/ask/speak") not in VISITOR_ASK_PATHS


def test_a_visitor_sees_what_a_dispatcher_sees(client: TestClient) -> None:
    enter(client)
    assert client.get("/api/desk/advisories").status_code == 200
    assert client.get("/api/desk/ai-failures").status_code == 200


# --- dispatchers ---------------------------------------------------------------------------


def test_a_dispatcher_session_is_unchanged(client: TestClient) -> None:
    body = login(client).json()
    assert (body["role"], body["name"]) == ("dispatcher", DISPATCHER)
    assert client.get("/api/desk/me").json()["role"] == "dispatcher"
    assert approve(client).json()["decided_by"] == f"desk:{DISPATCHER}"
    assert client.post("/api/mode", json={"mode": "LIVE"}).status_code == 200
    decisions: Counter[str] = client.app.state.visitor_decisions  # type: ignore[attr-defined]
    assert sum(decisions.values()) == 0


def test_a_session_minted_before_roles_existed_is_a_dispatcher(
    tmp_path: Path, client: TestClient
) -> None:
    """Push-1 cookies carry no role claim; they survive the push that adds roles."""
    settings = make_settings(tmp_path)
    at = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    token = forge_token({"n": "Ana K", "exp": 4102444800, "sid": "0011223344556677"})
    session = verify_session(token, settings, at=at)
    assert session is not None
    assert (session.role, session.sid) == ("dispatcher", "0011223344556677")
    client.cookies.set("tephra_desk", token)
    assert client.get("/api/desk/me").json()["role"] == "dispatcher"
    assert client.post("/api/mode", json={"mode": "LIVE"}).status_code == 200


def test_an_unknown_role_or_a_visitor_without_a_session_id_is_no_session(
    tmp_path: Path,
) -> None:
    settings = make_settings(tmp_path)
    at = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    base = {"n": "Ana K", "exp": 4102444800}
    assert verify_session(forge_token({**base, "r": "admin", "sid": "00"}), settings, at=at) is None
    assert verify_session(forge_token({**base, "r": "visitor"}), settings, at=at) is None
    assert verify_session(forge_token({**base, "r": "visitor", "sid": 7}), settings, at=at) is None
    ok = verify_session(forge_token({**base, "r": "visitor", "sid": "ab"}), settings, at=at)
    assert ok is not None
    assert ok.role == "visitor"


def test_the_state_says_when_a_visitor_may_enter(client: TestClient, harness: Harness) -> None:
    assert client.get("/api/state").json()["visitor_access"] is True
    harness.runtime.mode = RunMode.LIVE
    assert client.get("/api/state").json()["visitor_access"] is False


def test_visitor_entered_is_an_audit_action() -> None:
    assert AuditAction.VISITOR_ENTERED.value == "VISITOR_ENTERED"
