"""The airline path rewrite, the route table and the one dependency (tephra.api.tenancy).

A stand-in registry and access cache (the parts tenant_scope reads) keep these tests about the
HTTP layer; tests/test_hosted_isolation.py runs the same rules over the real hosted domain.
"""

import asyncio
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.airline.sessions import AirlineClaims, sign_claims
from tephra.api import server
from tephra.api.auth import CSRF_HEADER, wall_clock_now
from tephra.api.server import create_app
from tephra.api.tenancy import (
    PAGE_KEY,
    REFUSED_KEY,
    ROUTE_INDEX,
    SCOPE_KEY,
    TENANT_ROUTES,
    TenantPathMiddleware,
    scoped_routes_missing,
    tenant_scope,
)
from tephra.config import Settings
from tephra.models import Connection, RunMode
from tephra.pipeline import Runtime
from tephra.store import open_store
from tephra.util import timeutil
from tephra.util.scope import current_tenant
from tests.test_api import FakeRuntime, Harness

SECRET = "hosted-session-secret-0123456789abcdef"
TASK_TOKEN = "task-token-for-tests-0123456789abcdef"
_PARAM = re.compile(r"\{[^}]+\}")


# --- stand-ins for the hosted domain ----------------------------------------------------


@dataclass
class FakeRecord:
    icao: str
    name: str
    state: str


@dataclass
class FakeHandle:
    record: FakeRecord
    runtime: Any = None


@dataclass
class FakeMember:
    id: str
    icao: str
    login_key: str
    display_name: str
    role: str


@dataclass
class FakeAccess:
    members: dict[tuple[str, str], FakeMember] = field(default_factory=dict)
    generation: int = 0
    lookups: int = 0

    def holds_member(self, login_key: str, icao: str) -> bool:
        return False

    async def member(
        self, store: Any, login_key: str, version: int, icao: str, *, record: Any = None
    ) -> FakeMember | None:
        self.lookups += 1
        return self.members.get((login_key, icao))


@dataclass
class FakeRegistry:
    handles: dict[str, FakeHandle] = field(default_factory=dict)
    keys: dict[tuple[str, str], Connection] = field(default_factory=dict)
    kicks: int = 0
    closed: bool = False

    def handle(self, icao: str) -> FakeHandle | None:
        return self.handles.get(icao)

    def push_key(self, icao: str, key: str) -> Connection | None:
        handle = self.handles.get(icao)
        if handle is None or handle.record.state in {"suspended", "deleting", "deleted"}:
            return None
        return self.keys.get((icao, key))

    def kick(self) -> None:
        self.kicks += 1

    async def start_all(self) -> None:
        return None

    async def aclose(self) -> None:
        self.closed = True


def hosted_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "llm": "stub",
        "store": "sqlite",
        "sqlite_path": tmp_path / "tephra.sqlite3",
        "cache_dir": tmp_path / "cache",
        "data_dir": tmp_path / "data",
        "desk_pin": "zulu-4711",
        "task_token": TASK_TOKEN,
        "session_secret": SECRET,
        "local_scheduler": False,
        "features": "connect,crew,notices,onboard,hosted",
    }
    return Settings(_env_file=None, **{**values, **overrides})


class FakeHosted:
    """An app with ``hosted`` on, a stand-in demo runtime, and RFB (shadow) and RFC (live) as
    stand-in airlines, each with its own store."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.harness = Harness()
        self.registry = FakeRegistry()
        self.access = FakeAccess()
        self.tenants: dict[str, FakeRuntime] = {}
        for icao, name, state in (
            ("RFB", "Ring of Fire Charter", "shadow"),
            ("RFC", "Ring of Fire Cargo", "live"),
        ):
            tenant = settings.model_copy(
                update={"sqlite_path": settings.sqlite_path.parent / f"{icao}.sqlite3"}
            )
            runtime = FakeRuntime(settings=tenant, store=open_store(tenant))
            self.tenants[icao] = runtime
            self.registry.handles[icao] = FakeHandle(FakeRecord(icao, name, state), runtime)

    async def runtime_factory(self, settings: Settings, *, meter: Any = None) -> Runtime:
        return await self.harness.factory(settings)

    def registry_factory(self, *args: Any) -> Any:
        return self.registry

    def app(self) -> FastAPI:
        app = create_app(
            self.settings,
            runtime_factory=self.runtime_factory,
            registry_factory=self.registry_factory,
        )
        app.state.access = self.access
        return app

    def member(self, icao: str, role: str, login_key: str = "k-ana") -> FakeMember:
        member = FakeMember(f"MB-{icao.lower()}0000001", icao, login_key, "Ana Ops", role)
        self.access.members[(login_key, icao)] = member
        return member


def airline_cookie(settings: Settings, login_key: str = "k-ana", version: int = 1) -> str:
    claims = AirlineClaims("AL-0123456789ab", login_key, version, "", "")
    token, _ = sign_claims(claims, settings, at=wall_clock_now())
    return token


def concrete(template: str) -> str:
    return _PARAM.sub("x", template)


@pytest.fixture
def hosted(tmp_path: Path) -> FakeHosted:
    return FakeHosted(hosted_settings(tmp_path))


@pytest.fixture
def client(hosted: FakeHosted) -> Iterator[TestClient]:
    with TestClient(hosted.app()) as test_client:
        yield test_client


# --- the path rewrite -------------------------------------------------------------------


class Recorder:
    def __init__(self) -> None:
        self.scope: Scope | None = None
        self.tenant: str | None = None
        self.bound = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        self.scope = scope
        self.tenant = current_tenant()
        self.bound = timeutil.clock_bound()


def run_middleware(path: str, raw_path: bytes | None = None) -> Recorder:
    recorder = Recorder()
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode(),
        "query_string": b"",
        "headers": [],
    }

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        return None

    asyncio.run(TenantPathMiddleware(recorder)(scope, receive, send))
    return recorder


def test_an_airline_api_path_becomes_the_site_s_with_the_airline_bound() -> None:
    seen = run_middleware("/a/RFB/api/desk/advisories")
    assert seen.scope is not None
    assert seen.scope["path"] == "/api/desk/advisories"
    assert seen.scope["raw_path"] == b"/api/desk/advisories"
    assert seen.scope[SCOPE_KEY] == "RFB"
    assert (seen.tenant, seen.bound) == ("RFB", True)
    assert current_tenant() is None
    assert not timeutil.clock_bound()


def test_an_airline_page_passes_unchanged_and_a_root_path_untouched() -> None:
    page = run_middleware("/a/RFB/settings/people")
    assert page.scope is not None
    assert page.scope["path"] == "/a/RFB/settings/people"
    assert page.scope[PAGE_KEY] == "RFB"
    assert SCOPE_KEY not in page.scope
    assert page.tenant == "RFB"
    root = run_middleware("/api/state")
    assert root.scope is not None
    assert SCOPE_KEY not in root.scope
    assert root.tenant is None
    assert run_middleware("/about").tenant is None


@pytest.mark.parametrize(
    ("path", "raw"),
    [
        ("/a/rfb/api/state", None),
        ("/a/RFBX/api/state", None),
        ("/a/RF/api/state", None),
        ("/a/RFB/api/../api/mode", None),
        ("/a/RFB//api/state", None),
        ("/a/RFB/api/./state", None),
        ("/a/RFB/api/..", None),
        ("/a/RFB/api/../mode", b"/a/RFB/api/%2e%2e/mode"),
        ("/a/RFB/api/../mode", b"/a/RFB/api/%2E%2E/mode"),
        ("/a/RFB/api/blobs/../x", b"/a/RFB/api/blobs/..%2Fx"),
        ("/a/RFB/api/blobs/..\\x", b"/a/RFB/api/blobs/..%5cx"),
        ("/a/RFB/api/state", b"/a/%52FB/api/state"),
    ],
)
def test_tricky_airline_paths_are_refused(path: str, raw: bytes | None) -> None:
    seen = run_middleware(path, raw)
    assert seen.scope is not None
    assert seen.scope.get(REFUSED_KEY) is True
    assert SCOPE_KEY not in seen.scope
    assert seen.tenant is None


TRICKS = [
    "/a/rfb/api/state",
    "/a/RFBX/api/state",
    "/a/RFB/api/../api/mode",
    "/a/RFB//api/state",
    "/a/RFB/api/%2e%2e/mode",
    "/a/RFB/api/blobs/..%2Fx",
    "/a/rfb/",
    "/a/RFB/settings/..",
]


async def raw_get(app: FastAPI, raw_path: bytes, cookie: str) -> tuple[int, bytes]:
    """One GET over ASGI with the path exactly as given (an HTTP client would normalise
    the dot segments away before sending)."""
    path = raw_path.decode().replace("%2e", ".").replace("%2F", "/")
    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": raw_path,
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"cookie", cookie.encode())],
        "client": ("127.0.0.1", 1),
        "server": ("testserver", 80),
        "state": {},
    }
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b""}

    async def send(message: Message) -> None:
        sent.append(message)

    await app(scope, receive, send)
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return sent[0]["status"], body


@pytest.mark.parametrize("path", TRICKS)
def test_tricky_paths_answer_404_through_the_app(
    client: TestClient, hosted: FakeHosted, path: str
) -> None:
    hosted.member("RFB", "ops_manager")
    cookie = f"{AIRLINE_COOKIE}={airline_cookie(hosted.settings)}"
    status, body = client.portal.call(raw_get, cast(FastAPI, client.app), path.encode(), cookie)  # type: ignore[union-attr]
    assert status == 404, body
    assert json.loads(body)["error"] in {"not_found", "not_hosted"}


def test_a_wrong_method_under_an_airline_is_not_hosted_too(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "ops_manager")
    response = client.get("/a/RFB/api/mode")
    assert response.status_code == 404
    assert response.json()["error"] == "not_hosted"
    assert "allow" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/mode").status_code == 405


# --- the route table --------------------------------------------------------------------


def member_cookie(client: TestClient, hosted: FakeHosted, icao: str, role: str) -> None:
    hosted.member(icao, role)
    client.cookies.set(AIRLINE_COOKIE, airline_cookie(hosted.settings))


def api_contexts(app: FastAPI) -> list[tuple[str, str, list[Any]]]:
    found = []
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute):
            (method,) = context.methods
            found.append((method, str(context.path_format), list(context.dependencies)))
    return found


def test_every_api_and_task_route_carries_the_airline_check(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    routes = [r for r in api_contexts(app) if r[1].startswith(("/api/", "/tasks/"))]
    assert len(routes) > 100
    for method, path, dependencies in routes:
        assert any(d.dependency is tenant_scope for d in dependencies), f"{method} {path}"
    assert scoped_routes_missing(app) == []


def test_every_table_entry_names_a_real_route(client: TestClient) -> None:
    served = set(ROUTE_INDEX.values())
    assert set(TENANT_ROUTES) <= served, sorted(set(TENANT_ROUTES) - served)
    assert all(path.startswith("/api/") for _, path in TENANT_ROUTES)


def test_every_route_outside_the_table_answers_not_hosted(
    client: TestClient, hosted: FakeHosted
) -> None:
    """Over the whole inventory of one app, signed in as the airline's ops manager."""
    member_cookie(client, hosted, "RFB", "ops_manager")
    outside = [
        (method, path)
        for method, path, _ in api_contexts(cast(FastAPI, client.app))
        if path.startswith(("/api/", "/tasks/")) and (method, path) not in TENANT_ROUTES
    ]
    assert ("POST", "/api/mode") in outside
    assert ("GET", "/api/blobs/{key}") in outside
    assert ("GET", "/api/audit/verify") in outside
    assert ("POST", "/tasks/tick") in outside
    assert ("GET", "/api/hosted/me") in outside
    assert ("GET", "/api/admin/me") in outside
    headers = {CSRF_HEADER: "1", "X-Tephra-Task-Token": TASK_TOKEN}
    for method, path in outside:
        response = client.request(method, "/a/RFB" + concrete(path), json={}, headers=headers)
        assert response.status_code == 404, f"{method} {path}: {response.status_code}"
        # /a/<ICAO>/tasks/... is no airline API path at all: no route serves it
        expected = "not_found" if path.startswith("/tasks/") else "not_hosted"
        assert response.json()["error"] == expected, f"{method} {path}"


def test_the_app_refuses_to_start_with_an_unchecked_route(
    hosted: FakeHosted, monkeypatch: pytest.MonkeyPatch
) -> None:
    stray = APIRouter()

    @stray.get("/api/stray")
    async def stray_route() -> dict[str, str]:
        return {}

    real = server._include_hosted_routers

    def with_stray(app: FastAPI, dependencies: list[Any]) -> None:
        real(app, dependencies)
        app.include_router(stray)

    monkeypatch.setattr(server, "_include_hosted_routers", with_stray)
    with pytest.raises(RuntimeError, match="GET /api/stray"):
        hosted.app()


def test_the_rank_table_agrees_with_the_hosted_models() -> None:
    from tephra.api.tenancy import _RANK
    from tephra.hosted.models import ROLE_RANK

    assert dict(ROLE_RANK) == _RANK


# --- hosted off: nothing of it exists ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/a/RFB/api/state",
        "/a/RFB/",
        "/a/RFB/desk",
        "/a/RFB/settings/people",
        "/api/tenant/header",
        "/api/hosted/me",
        "/join",
    ],
)
def test_with_hosted_off_no_hosted_route_or_page_exists(tmp_path: Path, path: str) -> None:
    settings = hosted_settings(tmp_path, features="connect,onboard")
    app = create_app(settings, runtime_factory=Harness().factory)
    assert not any(m.cls is TenantPathMiddleware for m in app.user_middleware)
    with TestClient(app) as client:
        assert client.get(path).status_code == 404


def test_with_hosted_off_no_route_is_given_the_check(tmp_path: Path) -> None:
    settings = hosted_settings(tmp_path, features="connect,onboard")
    app = create_app(settings, runtime_factory=Harness().factory)
    assert {path for _, path in TENANT_ROUTES if path.startswith("/api/tenant/")}.isdisjoint(
        path for _, path, _ in api_contexts(app)
    )
    for _, _, dependencies in api_contexts(app):
        assert not any(d.dependency is tenant_scope for d in dependencies)


# --- the dependency ---------------------------------------------------------------------


def test_a_member_reads_the_airline_s_runtime_and_the_demo_stays_its_own(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    hosted.tenants["RFB"].mode = RunMode.REPLAY
    tenant = client.get("/a/RFB/api/state")
    assert tenant.status_code == 200, tenant.text
    assert tenant.json()["mode"] == "REPLAY"
    assert client.get("/api/state").json()["mode"] == "LIVE"


def test_signed_out_is_401_and_a_stranger_is_404_like_a_missing_airline(
    client: TestClient, hosted: FakeHosted
) -> None:
    assert client.get("/a/RFB/api/state").json()["error"] == "unauthenticated"
    member_cookie(client, hosted, "RFC", "ops_manager")
    stranger = client.get("/a/RFB/api/state")
    missing = client.get("/a/RFZ/api/state")
    assert stranger.status_code == missing.status_code == 404
    assert stranger.json() == missing.json()
    assert stranger.json()["error"] == "no_such_airline"


def test_roles_states_and_limits(client: TestClient, hosted: FakeHosted) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    approve = client.post(
        "/a/RFB/api/desk/advisories/adv_0123456789ab/approve", json={"version": 1}
    )
    assert (approve.status_code, approve.json()["error"]) == (403, "role")
    assert "is Viewer" in approve.json()["detail"]
    upload = client.post("/a/RFB/api/desk/upload", json={"format": "tephra.positions/1"})
    assert upload.json()["detail"] == "Only an ops manager can do this."
    assert client.get("/a/RFB/api/advisories?limit=51").json()["error"] == "limit_too_large"
    assert client.get("/a/RFB/api/advisories?limit=50").status_code == 200
    hosted.registry.handles["RFB"].record.state = "setup"
    assert client.get("/a/RFB/api/state").json()["error"] == "not_started"
    hosted.registry.handles["RFB"].record.state = "suspended"
    assert client.get("/a/RFB/api/state").json()["error"] == "tenant_suspended"
    assert client.get("/a/RFB/api/desk/me").status_code == 200
    hosted.registry.handles["RFB"].record.state = "deleted"
    assert client.get("/a/RFB/api/desk/me").json()["error"] == "no_such_airline"


def test_a_member_s_desk_session_is_named_by_member_and_never_a_desk_cookie(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "dispatcher")
    me = client.get("/a/RFB/api/desk/me").json()
    assert (me["name"], me["role"], me["sid"]) == ("Ana Ops", "dispatcher", "MB-rfb0000001")
    viewer = hosted.member("RFC", "viewer")
    assert client.get("/a/RFC/api/desk/me").json()["role"] == "viewer"
    assert viewer.role == "viewer"
    # the airline cookie is not a Desk session at the root
    assert client.get("/api/desk/me").json()["error"] == "unauthenticated"


def test_the_member_lookup_counts_the_request_throttles(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    before = hosted.access.lookups
    client.get("/a/RFB/api/desk/me")
    assert hosted.access.lookups == before + 1
    state = cast(FastAPI, client.app).state
    assert state.airline_requests.remaining("testclient") < 60
    # never the site-wide count: a self-made account spending it locked every airline out
    assert state.airline_requests_all.remaining("site") == 5000


def test_a_spent_site_wide_request_count_locks_no_member_out(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    throttle = cast(FastAPI, client.app).state.airline_requests_all
    while not throttle.blocked("site"):
        throttle.record_failure("site")
    assert client.get("/a/RFB/api/desk/me").status_code == 200


@pytest.mark.parametrize(
    "given", ["51", "+200", "0200", "200.0", "%20200", "%EF%BC%92%EF%BC%90%EF%BC%90", "1e3"]
)
def test_every_spelling_of_a_large_limit_is_refused(
    client: TestClient, hosted: FakeHosted, given: str
) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    response = client.get(f"/a/RFB/api/advisories?limit={given}")
    assert (response.status_code, response.json()["error"]) == (422, "limit_too_large")


@pytest.mark.parametrize("path", ["/a/RFB/api/state/", "/a/RFB/api/tenant/header/", "/a/RFB/api/"])
def test_a_trailing_slash_under_an_airline_never_redirects_to_the_demo(
    client: TestClient, hosted: FakeHosted, path: str
) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers


def test_the_site_s_schema_is_not_an_airline_route(client: TestClient, hosted: FakeHosted) -> None:
    member_cookie(client, hosted, "RFB", "viewer")
    assert client.get("/a/RFB/api/openapi.json").status_code == 404
    assert client.get("/api/openapi.json").status_code == 200


def test_once_an_airline_s_reads_are_spent_its_reads_stop_and_writes_go_through(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "dispatcher")
    state = cast(FastAPI, client.app).state
    state.meter.count("RFB", "reads", state.meter.ceiling(hosted.settings))
    refused = client.get("/a/RFB/api/state")
    assert (refused.status_code, refused.json()["error"]) == (503, "airline_paused")
    assert "00:00 Pacific" in refused.json()["detail"]
    approve = client.post(
        "/a/RFB/api/desk/advisories/adv_0123456789ab/approve",
        json={"version": 1},
        headers={CSRF_HEADER: "1"},
    )
    assert approve.json().get("error") != "airline_paused"
    assert client.get("/api/state").status_code == 200  # the demo is not the airline
    member_cookie(client, hosted, "RFC", "viewer")
    assert client.get("/a/RFC/api/state").status_code == 200  # nor another airline


def test_the_tick_task_kicks_the_hosted_pass_first(client: TestClient, hosted: FakeHosted) -> None:
    response = client.post("/tasks/tick", headers={"X-Tephra-Task-Token": TASK_TOKEN})
    assert response.status_code == 200
    assert hosted.registry.kicks == 1


def test_the_registry_closes_before_the_demo_runtime(tmp_path: Path) -> None:
    hosted = FakeHosted(hosted_settings(tmp_path))
    with TestClient(hosted.app()):
        pass
    assert hosted.registry.closed
    assert hosted.harness.runtime.closed


def test_hosted_on_takes_the_model_keys_out_of_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    FakeHosted(hosted_settings(tmp_path)).app()
    assert "GOOGLE_API_KEY" not in os.environ
    assert "GEMINI_API_KEY" not in os.environ


def test_hosted_off_leaves_the_environment_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    monkeypatch.setenv("GEMINI_API_KEY", "test-key-BBBBBBBBBBBBBBBBBBBBBBBBBBBBBB")
    create_app(hosted_settings(tmp_path, features="onboard"), runtime_factory=Harness().factory)
    assert "GEMINI_API_KEY" in os.environ


# --- sessions, actors and logs -------------------------------------------------------------


def test_a_desk_cookie_never_carries_the_viewer_role(hosted: FakeHosted) -> None:
    from tephra.api.auth import sign_session, verify_session

    at = wall_clock_now()
    token, _ = sign_session("Vic", hosted.settings, at=at, role="viewer", sid="0011223344556677")
    assert verify_session(token, hosted.settings, at=at) is None
    good, _ = sign_session("Dee", hosted.settings, at=at)
    assert verify_session(good, hosted.settings, at=at) is not None


def test_a_member_decides_as_name_and_member_id_and_the_demo_as_today() -> None:
    from datetime import timedelta

    from tephra.api.auth import actor_of
    from tephra.models import SessionInfo
    from tephra.util.scope import bind_tenant

    session = SessionInfo(
        name="Dee D", expires_at=wall_clock_now() + timedelta(hours=1), sid="MB-0123456789"
    )
    assert actor_of(session) == "desk:Dee D"
    with bind_tenant("RFB"):
        assert actor_of(session) == "desk:Dee D#MB-0123456789"
    visitor = session.model_copy(update={"role": "visitor"})
    with bind_tenant("RFB"):
        assert actor_of(visitor) == "visitor:Dee D"


def test_a_log_line_written_for_an_airline_names_it() -> None:
    import logging

    from tephra.api.server import JsonLogFormatter
    from tephra.util.scope import bind_tenant

    record = logging.LogRecord("tephra.x", logging.INFO, __file__, 1, "pushed", None, None)
    formatter = JsonLogFormatter()
    assert "tenant" not in json.loads(formatter.format(record))
    with bind_tenant("RFB"):
        assert json.loads(formatter.format(record))["tenant"] == "RFB"


def test_a_wrong_method_answers_the_same_body_as_a_route_outside_the_table(
    client: TestClient, hosted: FakeHosted
) -> None:
    member_cookie(client, hosted, "RFB", "ops_manager")
    assert client.get("/a/RFB/api/mode").json() == client.post("/a/RFB/api/mode", json={}).json()
