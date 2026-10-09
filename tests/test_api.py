"""HTTP API tests: FastAPI TestClient over a stand-in runtime, the real SQLite store and desk.

No network and no model. The stand-in replaces ``tephra.pipeline.Runtime`` (its tick
returns a canned report and the LLM label is the stub's NO MODEL); advisories go through
``tephra.desk.approvals`` exactly as in production.
"""

import base64
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tephra.api.auth import COOKIE_NAME, TASK_HEADER, LoginThrottle, sign_session, verify_session
from tephra.api.server import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES, create_app
from tephra.api.sse import event_stream, format_event, parse_last_event_id
from tephra.config import AIRLINE_CODE, AIRLINE_NAME, DISCLAIMER, NO_MODEL_LABEL, Settings
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AirlineInfo,
    FeedHealth,
    FeedId,
    FeedStatus,
    LlmInfo,
    Overlays,
    PlumeMode,
    ReplayCase,
    RunMode,
    SseEvent,
    SystemState,
    TickReport,
    TraceEvent,
    TraceStage,
    WallSnapshot,
    feature_collection,
)
from tephra.pipeline import Runtime
from tephra.store import open_store
from tephra.store.base import Store
from tephra.util import timeutil
from tephra.util.events import Event, EventBus
from tephra.util.hashing import proxy_flight_number

PIN = "zulu-4711"
TASK_TOKEN = "task-token-for-tests"
ADVISORY_ID = "adv_0123456789ab"
DISPATCHER = "Ana K"
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


# --- a stand-in runtime -----------------------------------------------------------------


@dataclass
class FakeRuntime:
    """The parts of ``tephra.pipeline.Runtime`` the API touches."""

    settings: Settings
    store: Store
    bus: EventBus = field(default_factory=EventBus)
    mode: RunMode = RunMode.LIVE
    replay_case: ReplayCase | None = None
    auto_replay: bool = False
    ticks: int = 0
    fail_tick: bool = False
    closed: bool = False

    async def tick(self, *, reason: str = "scheduler") -> TickReport:
        if self.fail_tick:
            raise RuntimeError("database password is hunter2")
        self.ticks += 1
        at = timeutil.now()
        return TickReport(started_at=at, finished_at=at, mode=self.mode, reason=reason)

    async def system_state(self) -> SystemState:
        at = timeutil.now()
        return SystemState(
            mode=self.mode,
            now=at,
            server_time=at,
            replay=None,
            llm=LlmInfo(backend="stub", model_id="stub", label=NO_MODEL_LABEL),
            airline=AirlineInfo(code=AIRLINE_CODE, name=AIRLINE_NAME),
            disclaimer=DISCLAIMER,
            region=self.settings.region_preset,
            regions=self.settings.regions,
            feeds=[FeedHealth(feed=FeedId.SIGMET, status=FeedStatus.NEVER, cadence_s=60)],
            active_volcano_ids=[],
            exposed_count=0,
            draft_count=1,
        )

    async def wall_snapshot(self) -> WallSnapshot:
        return WallSnapshot(
            generated_at=timeutil.now(),
            volcanoes=feature_collection([]),
            official=feature_collection([]),
            cones=feature_collection([]),
            exposures=feature_collection([]),
            aircraft=feature_collection([]),
            situations=[],
            overlays=Overlays(),
        )

    async def switch_mode(self, mode: RunMode, *, auto: bool = False) -> None:
        self.mode = mode

    async def aclose(self) -> None:
        self.closed = True
        await self.store.aclose()


def make_advisory() -> Advisory:
    at = timeutil.now()
    hex_id = "8a0123"
    return Advisory(
        id=ADVISORY_ID,
        version=1,
        status=AdvisoryStatus.DRAFT,
        created_at=at,
        updated_at=at,
        replay=False,
        volcano_id="263300",
        volcano_name="Semeru",
        flight_id=f"{hex_id}:263300",
        proxy_flight=proxy_flight_number(hex_id),
        callsign="GIA417",
        hex=hex_id,
        type_icao="B738",
        action=ActionKind.HOLD,
        hold_fl=350,
        minutes_to_entry=14,
        inside_now=False,
        fuel_line="HOLD 20 MIN x 42 KG/MIN (NARROWBODY) = 840 KG",
        plume_mode=PlumeMode.OFFICIAL,
        confidence=1.0,
        cone_id="CONE-0123456789ab",
        assessment_id="PA-0123456789ab",
        plan_id="PLAN-0123456789ab",
        header="TEPHRA COMPANY ADVISORY - RING OF FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL USE",
        body="HOLD PRESENT POSITION FL350. ASH SFC/FL150 AHEAD, ENTRY 14 MIN. REPORT VAR.",
        cost_note="HOLD 20 MIN 840 KG",
        sources=[],
        input_hash="0" * 64,
        llm_backend="stub",
        model_id="stub",
        prompt_hashes={"plume_reader": "a" * 64, "planner": "b" * 64, "drafter": "c" * 64},
        dedupe_key="DD-0123456789ab",
    )


class Harness:
    """Builds the stand-in runtime inside the app's lifespan and keeps a handle on it."""

    def __init__(self) -> None:
        self._runtime: FakeRuntime | None = None

    @property
    def runtime(self) -> FakeRuntime:
        assert self._runtime is not None, "app not started"
        return self._runtime

    async def factory(self, settings: Settings) -> Runtime:
        store = open_store(settings)
        created = await store.compare_and_set_advisory(
            ADVISORY_ID, 0, make_advisory().model_dump(mode="json")
        )
        assert created
        self._runtime = FakeRuntime(settings=settings, store=store)
        return cast(Runtime, self._runtime)


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        task_token=TASK_TOKEN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


@pytest.fixture
def harness() -> Harness:
    return Harness()


@pytest.fixture
def client(settings: Settings, harness: Harness) -> Iterator[TestClient]:
    app = create_app(settings, runtime_factory=harness.factory)
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient, *, pin: str = PIN, name: str = DISPATCHER) -> httpx.Response:
    return client.post("/api/desk/login", json={"pin": pin, "name": name})


def error_of(response: httpx.Response) -> str:
    return str(response.json()["error"])


# --- pages, headers, read API -----------------------------------------------------------


def test_healthz_carries_security_headers(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "mode": "LIVE"}
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-cache"


def test_csp_allows_no_inline_code() -> None:
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY
    assert "'unsafe-eval'" not in CONTENT_SECURITY_POLICY
    assert "script-src 'self' https://unpkg.com" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


@pytest.mark.parametrize("path", ["/", "/desk"])
def test_pages_are_html_with_csp(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["cache-control"] == "no-cache"


def test_state_is_labelled_fictional_and_no_model(client: TestClient) -> None:
    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["mode"] == "LIVE"
    assert body["airline"] == {"code": "RFA", "name": "Ring of Fire Air", "fictional": True}
    assert body["disclaimer"] == DISCLAIMER
    assert body["llm"]["label"] == NO_MODEL_LABEL
    assert ISO_UTC.fullmatch(body["now"])


def test_wall_bundles_state_snapshot_advisories_and_trace(
    client: TestClient, harness: Harness
) -> None:
    harness.runtime.bus.publish(
        SseEvent.TRACE, TraceEvent.new(TraceStage.SYSTEM, "code", "tick started")
    )
    response = client.get("/api/wall")
    assert response.status_code == 200
    body = response.json()
    assert body["state"]["mode"] == "LIVE"
    assert body["snapshot"]["cones"] == {"type": "FeatureCollection", "features": []}
    assert [advisory["id"] for advisory in body["advisories"]] == [ADVISORY_ID]
    assert body["trace"][-1]["message"] == "tick started"


def test_advisories_filter_by_status(client: TestClient) -> None:
    drafts = client.get("/api/advisories", params={"status": "DRAFT"}).json()["advisories"]
    assert [advisory["id"] for advisory in drafts] == [ADVISORY_ID]
    assert client.get("/api/advisories?status=APPROVED").json() == {"advisories": []}
    bad = client.get("/api/advisories?status=BOGUS")
    assert bad.status_code == 422
    assert error_of(bad) == "validation_failed"
    assert client.get("/api/advisories?limit=0").status_code == 422


def test_feeds_and_replays(client: TestClient) -> None:
    feeds = client.get("/api/feeds").json()["feeds"]
    assert feeds[0]["feed"] == "sigmet"
    assert client.get("/api/replays").json() == {"cases": []}


def test_blobs_serve_only_known_keys(client: TestClient, harness: Harness) -> None:
    key = "frames/263300_B13_IR_20261009T1930Z.png"
    client.portal.call(harness.runtime.store.put_blob, key, PNG_BYTES, "image/png")
    found = client.get(f"/api/blobs/{key}")
    assert found.status_code == 200
    assert found.content == PNG_BYTES
    assert found.headers["content-type"] == "image/png"
    for bad in ("frames/x.txt", "other/x.png", "frames/missing.png"):
        response = client.get(f"/api/blobs/{bad}")
        assert response.status_code == 404
        assert error_of(response) == "not_found"


def test_unknown_route_is_error_body(client: TestClient) -> None:
    response = client.get("/api/nothing-here")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


# --- desk login -------------------------------------------------------------------------


def test_login_sets_strict_httponly_cookie_and_audits(client: TestClient) -> None:
    response = login(client)
    assert response.status_code == 200
    assert response.json()["name"] == DISPATCHER
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{COOKIE_NAME}=")
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "secure" not in cookie
    me = client.get("/api/desk/me")
    assert me.status_code == 200
    assert me.json()["name"] == DISPATCHER
    audit = client.get("/api/audit")
    actions = [(entry["action"], entry["actor"]) for entry in audit.json()["entries"]]
    assert ("LOGIN_OK", f"desk:{DISPATCHER}") in actions
    assert PIN not in audit.text


def test_secure_cookie_behind_https_proxy(client: TestClient) -> None:
    response = client.post(
        "/api/desk/login",
        json={"pin": PIN, "name": DISPATCHER},
        headers={"X-Forwarded-Proto": "https"},
    )
    assert response.status_code == 200
    assert "secure" in response.headers["set-cookie"].lower()


def test_bad_pin_then_throttled(client: TestClient) -> None:
    for _ in range(5):
        response = login(client, pin="wrong-pin")
        assert response.status_code == 401
        assert error_of(response) == "bad_pin"
    blocked = login(client)
    assert blocked.status_code == 429
    assert error_of(blocked) == "too_many_attempts"
    assert int(blocked.headers["retry-after"]) > 0
    failures = [
        entry
        for entry in client.get("/api/audit").json()["entries"]
        if entry["action"] == "LOGIN_FAILED"
    ]
    assert len(failures) == 5


def test_login_validation_never_echoes_the_pin(client: TestClient) -> None:
    secret = "x" * 64 + "topsecretpin"
    response = client.post("/api/desk/login", json={"pin": secret, "name": DISPATCHER})
    assert response.status_code == 422
    assert error_of(response) == "validation_failed"
    assert response.json()["problems"]
    assert "topsecretpin" not in response.text


def test_login_rejects_markup_in_name(client: TestClient) -> None:
    response = login(client, name="<script>")
    assert response.status_code == 422
    assert error_of(response) == "validation_failed"


def test_login_refuses_cross_site_requests(client: TestClient) -> None:
    form = client.post("/api/desk/login", data={"pin": PIN, "name": DISPATCHER})
    assert form.status_code == 403
    assert error_of(form) == "forbidden"
    cross_origin = client.post(
        "/api/desk/login",
        json={"pin": PIN, "name": DISPATCHER},
        headers={"Origin": "https://evil.example"},
    )
    assert cross_origin.status_code == 403
    fetch_metadata = client.post(
        "/api/desk/login",
        json={"pin": PIN, "name": DISPATCHER},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert fetch_metadata.status_code == 403


def test_oversized_body_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/desk/login",
        content=b"{" + b" " * (MAX_BODY_BYTES + 1) + b"}",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert error_of(response) == "too_large"


def test_desk_disabled_without_pin(settings: Settings, harness: Harness) -> None:
    app = create_app(
        settings.model_copy(update={"desk_pin": None}), runtime_factory=harness.factory
    )
    with TestClient(app) as test_client:
        response = login(test_client)
        assert response.status_code == 503
        assert error_of(response) == "desk_disabled"
        assert test_client.get("/api/desk/advisories").status_code == 503


def test_logout_clears_the_cookie(client: TestClient) -> None:
    login(client)
    response = client.post("/api/desk/logout")
    assert response.status_code == 204
    assert f"{COOKIE_NAME}=" in response.headers["set-cookie"]
    assert client.get("/api/desk/me").status_code == 401


# --- desk decisions ---------------------------------------------------------------------


def test_desk_endpoints_need_a_session(client: TestClient) -> None:
    listing = client.get("/api/desk/advisories")
    assert listing.status_code == 401
    assert error_of(listing) == "unauthenticated"
    approve = client.post(f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 1})
    assert approve.status_code == 401


def test_forged_cookie_is_rejected(client: TestClient) -> None:
    client.cookies.set(COOKIE_NAME, "eyJuIjoiTWFsbG9yeSJ9.c2lnbmF0dXJl")
    assert client.get("/api/desk/me").status_code == 401


def test_approve_queues_outbound_once(client: TestClient) -> None:
    login(client)
    drafts = client.get("/api/desk/advisories").json()["advisories"]
    assert [(advisory["id"], advisory["version"]) for advisory in drafts] == [(ADVISORY_ID, 1)]

    approved = client.post(f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 1})
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "APPROVED"
    assert body["version"] == 2
    assert body["decided_by"] == f"desk:{DISPATCHER}"

    outbound = client.get("/api/outbound").json()["messages"]
    assert [message["advisory_id"] for message in outbound] == [ADVISORY_ID]
    assert outbound[0]["destination"] == "tephra-outbound"

    again = client.post(f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 2})
    assert again.status_code == 409
    assert error_of(again) == "invalid_transition"
    assert len(client.get("/api/outbound").json()["messages"]) == 1


def test_stale_version_returns_current(client: TestClient) -> None:
    login(client)
    response = client.post(f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 7})
    assert response.status_code == 409
    assert error_of(response) == "version_conflict"
    assert response.json()["current"]["version"] == 1


def test_edit_keeps_both_versions(client: TestClient) -> None:
    login(client)
    response = client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/edit",
        json={"version": 1, "body": "hold present position fl350. report var."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "EDITED"
    assert body["edited_body"] == "HOLD PRESENT POSITION FL350. REPORT VAR."
    assert body["body"] == make_advisory().body
    assert body["final_body"] == body["edited_body"]


def test_edit_with_empty_body_is_validation_failed(client: TestClient) -> None:
    login(client)
    response = client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/edit", json={"version": 1, "body": ""}
    )
    assert response.status_code == 422
    assert error_of(response) == "validation_failed"


def test_reject_needs_a_reason(client: TestClient) -> None:
    login(client)
    short = client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/reject", json={"version": 1, "reason": "no"}
    )
    assert short.status_code == 422
    assert any("reason" in problem for problem in short.json()["problems"])
    rejected = client.post(
        f"/api/desk/advisories/{ADVISORY_ID}/reject",
        json={"version": 1, "reason": "Crew already holding on company frequency"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["reject_reason"] == "Crew already holding on company frequency"
    assert client.get("/api/outbound").json() == {"messages": []}


@pytest.mark.parametrize("advisory_id", ["adv_ffffffffffff", "not-an-id"])
def test_unknown_advisory_is_not_found(client: TestClient, advisory_id: str) -> None:
    login(client)
    response = client.post(f"/api/desk/advisories/{advisory_id}/approve", json={"version": 1})
    assert response.status_code == 404
    assert error_of(response) == "not_found"


# --- mode switch ------------------------------------------------------------------------


def test_mode_switch_needs_a_session(client: TestClient) -> None:
    response = client.post("/api/mode", json={"mode": "REPLAY"})
    assert response.status_code == 401


def test_mode_switch_is_audited(client: TestClient, harness: Harness) -> None:
    login(client)
    response = client.post("/api/mode", json={"mode": "LIVE"})
    assert response.status_code == 200
    assert response.json()["mode"] == "LIVE"
    entries = client.get("/api/audit").json()["entries"]
    switches = [entry for entry in entries if entry["action"] == "MODE_SWITCH"]
    assert switches
    assert switches[0]["actor"] == f"desk:{DISPATCHER}"


def test_mode_switch_to_unknown_case(client: TestClient, harness: Harness) -> None:
    login(client)
    missing = client.post("/api/mode", json={"mode": "REPLAY", "case_id": "no-such-case"})
    assert missing.status_code == 404
    assert harness.runtime.mode is RunMode.LIVE
    traversal = client.post("/api/mode", json={"mode": "REPLAY", "case_id": "../secrets"})
    assert traversal.status_code == 422


# --- scheduler task ---------------------------------------------------------------------


def test_tick_requires_the_task_token(client: TestClient, harness: Harness) -> None:
    assert client.post("/tasks/tick").status_code == 403
    wrong = client.post("/tasks/tick", headers={TASK_HEADER: "guess"})
    assert wrong.status_code == 403
    assert error_of(wrong) == "forbidden"
    assert harness.runtime.ticks == 0
    response = client.post("/tasks/tick", headers={TASK_HEADER: TASK_TOKEN})
    assert response.status_code == 200
    assert response.json()["reason"] == "scheduler"
    assert harness.runtime.ticks == 1


def test_tick_forbidden_when_token_unset(settings: Settings, harness: Harness) -> None:
    app = create_app(
        settings.model_copy(update={"task_token": None}), runtime_factory=harness.factory
    )
    with TestClient(app) as test_client:
        response = test_client.post("/tasks/tick", headers={TASK_HEADER: TASK_TOKEN})
        assert response.status_code == 403
        assert harness.runtime.ticks == 0


def test_internal_errors_carry_no_detail(settings: Settings, harness: Harness) -> None:
    app = create_app(settings, runtime_factory=harness.factory)
    with TestClient(app, raise_server_exceptions=False) as test_client:
        harness.runtime.fail_tick = True
        response = test_client.post("/tasks/tick", headers={TASK_HEADER: TASK_TOKEN})
        assert response.status_code == 500
        assert response.json()["error"] == "internal"
        assert "hunter2" not in response.text
        assert "Traceback" not in response.text


def test_runtime_closed_on_shutdown(settings: Settings, harness: Harness) -> None:
    with TestClient(create_app(settings, runtime_factory=harness.factory)):
        assert not harness.runtime.closed
    assert harness.runtime.closed


# --- sessions and throttle --------------------------------------------------------------


def test_session_roundtrip_expiry_and_forgery(settings: Settings) -> None:
    at = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
    token, expires_at = sign_session("Ana", settings, at=at)
    assert expires_at == at + timedelta(hours=settings.desk_session_ttl_h)

    session = verify_session(token, settings, at=at)
    assert session is not None
    assert session.name == "Ana"
    assert session.expires_at == expires_at
    assert verify_session(token, settings, at=expires_at) is None

    _, signature = token.split(".")
    forged_claims = {"n": "Mallory", "exp": int(expires_at.timestamp()), "sid": "00"}
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps(forged_claims).encode()).rstrip(b"=").decode()
    )
    assert verify_session(f"{forged_payload}.{signature}", settings, at=at) is None

    other = settings.model_copy(
        update={"session_secret": SecretStr("another-secret-entirely-0123456789")}
    )
    assert verify_session(token, other, at=at) is None
    for garbage in ("", "abc", "a.b.c", "!!!.???", "x" * 2000):
        assert verify_session(garbage, settings, at=at) is None


def test_login_throttle_window() -> None:
    clock = [1000.0]
    throttle = LoginThrottle(max_failures=2, window_s=10.0, clock=lambda: clock[0])
    throttle.record_failure("198.51.100.7")
    assert not throttle.blocked("198.51.100.7")
    throttle.record_failure("198.51.100.7")
    assert throttle.blocked("198.51.100.7")
    assert not throttle.blocked("198.51.100.8")
    assert 0 < throttle.retry_after_s("198.51.100.7") <= 11
    clock[0] += 10.5
    assert not throttle.blocked("198.51.100.7")
    throttle.record_failure("198.51.100.7")
    throttle.record_failure("198.51.100.7")
    throttle.clear("198.51.100.7")
    assert not throttle.blocked("198.51.100.7")


# --- Server-Sent Events -----------------------------------------------------------------


def test_format_event_framing_and_non_finite_numbers() -> None:
    at = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)
    event = Event(id=7, name="state", data={"a": 1, "x": float("nan")}, at=at)
    assert format_event(event) == 'id: 7\nevent: state\ndata: {"a":1,"x":null}\n\n'


def test_parse_last_event_id() -> None:
    assert parse_last_event_id("42") == 42
    assert parse_last_event_id(" 42 ") == 42
    for bad in (None, "", "x", "-1", "4.2", "١٢", "9" * 40):
        assert parse_last_event_id(bad) is None


async def test_event_stream_sends_events_then_heartbeats() -> None:
    bus = EventBus()
    stream = event_stream(bus, heartbeat_s=0.05, mode=lambda: RunMode.REPLAY)
    assert await anext(stream) == "retry: 3000\n\n"
    assert bus.subscriber_count == 1

    event = bus.publish(SseEvent.ADVISORY, {"id": ADVISORY_ID})
    assert await anext(stream) == (
        f'id: {event.id}\nevent: advisory\ndata: {{"id":"{ADVISORY_ID}"}}\n\n'
    )

    heartbeat = await anext(stream)
    assert heartbeat.startswith("event: heartbeat\ndata: ")
    payload = json.loads(heartbeat.split("data: ", 1)[1])
    assert payload["mode"] == "REPLAY"
    assert ISO_UTC.fullmatch(payload["now"])

    await stream.aclose()
    assert bus.subscriber_count == 0


async def test_event_stream_resumes_after_last_event_id() -> None:
    bus = EventBus()
    seen = bus.publish(SseEvent.TRACE, {"message": "seen"})
    missed_trace = bus.publish(SseEvent.TRACE, {"message": "missed"})
    missed_state = bus.publish(SseEvent.STATE, {"mode": "LIVE"})
    stream = event_stream(bus, heartbeat_s=5.0, last_event_id=seen.id)
    assert await anext(stream) == "retry: 3000\n\n"
    assert (await anext(stream)).startswith(f"id: {missed_trace.id}\nevent: trace\n")
    assert (await anext(stream)).startswith(f"id: {missed_state.id}\nevent: state\n")
    live = bus.publish(SseEvent.TRACE, {"message": "live"})
    assert (await anext(stream)).startswith(f"id: {live.id}\nevent: trace\n")
    await stream.aclose()
