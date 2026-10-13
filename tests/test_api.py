"""HTTP API tests: FastAPI TestClient over a stand-in runtime, the real SQLite store and desk.

No network and no model. The stand-in replaces ``tephra.pipeline.Runtime`` (its tick
returns a canned report and the LLM label is the stub's NO MODEL); advisories go through
``tephra.desk.approvals`` exactly as in production.
"""

import asyncio
import base64
import hashlib
import hmac
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from tephra.api.auth import (
    COOKIE_NAME,
    CSRF_HEADER,
    TASK_HEADER,
    LoginThrottle,
    sign_session,
    verify_session,
)
from tephra.api.server import CONTENT_SECURITY_POLICY, MAX_BODY_BYTES, create_app
from tephra.api.sse import event_stream, format_event, parse_last_event_id
from tephra.config import (
    AIRLINE_CODE,
    AIRLINE_NAME,
    DISCLAIMER,
    NO_MODEL_LABEL,
    PROJECT_ROOT,
    Settings,
)
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AiFailure,
    AirlineInfo,
    DutyRun,
    FeedHealth,
    FeedId,
    FeedStatus,
    LlmInfo,
    OperatorPolicy,
    Overlays,
    PlumeMode,
    PolicySummary,
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
from tephra.policy import load_policy
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import Event, EventBus
from tephra.util.hashing import proxy_flight_number

PIN = "zulu-4711"
TASK_TOKEN = "task-token-for-tests-0123456789abcdef"
ADVISORY_ID = "adv_0123456789ab"
DISPATCHER = "Ana K"
ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z")
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
POLICY = load_policy(PROJECT_ROOT / "data")


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
    startup_ticks: int = 0
    """The lifespan's own tick at startup, kept apart from the ticks a request asked for."""
    fail_tick: bool = False
    closed: bool = False
    policy: OperatorPolicy = field(default_factory=lambda: POLICY)
    policy_summary: PolicySummary = field(default_factory=lambda: PolicySummary.of(POLICY))
    replay_run_since: datetime | None = None
    airports: AirportCatalogue = field(
        default_factory=lambda: load_airports(
            PROJECT_ROOT / "data", min_runway_m=POLICY.alternates.min_runway_m.value
        )
    )

    async def tick(self, *, reason: str = "scheduler") -> TickReport:
        if self.fail_tick:
            raise RuntimeError("database password is hunter2")
        if reason == "startup":
            self.startup_ticks += 1
        else:
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
            policy=self.policy_summary,
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


FAILURE_ID = "AIF-0123456789ab"


def make_failure() -> AiFailure:
    hex_id = "8a0456"
    return AiFailure(
        id=FAILURE_ID,
        created_at=timeutil.now(),
        replay=False,
        stage="planner",
        reason="PLANNER AGENT ERROR: RuntimeError",
        model_id="gemini-3.5-flash-lite",
        volcano_id="263300",
        volcano_name="Semeru",
        flight_id=f"{hex_id}:263300",
        proxy_flight=proxy_flight_number(hex_id),
        hex=hex_id,
        cone_id="CONE-0123456789ab",
        minutes_to_entry=9,
        inside_now=False,
    )


def make_duty_runs() -> list[DutyRun]:
    """An older and a newer live run, and a replay run the live desk must not list."""
    at = timeutil.now()
    runs = []
    for n, (minutes, replay) in enumerate(((10, False), (2, False), (1, True))):
        started = at - timedelta(minutes=minutes)
        runs.append(
            DutyRun(
                id=f"DUTY-00000000000{n}",
                started_at=started,
                finished_at=started,
                replay=replay,
                trigger="tick",
                worklist=[],
                outcome="STUB",
                llm_backend="stub",
                model_id="stub",
                prompt_hash="0" * 64,
                recorded_wall_at=started,
            )
        )
    return runs


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
        await store.put(Collection.AI_FAILURES, FAILURE_ID, make_failure().model_dump(mode="json"))
        for run in make_duty_runs():
            await store.put(Collection.DUTY, run.id, run.model_dump(mode="json"))
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


def login(
    client: TestClient,
    *,
    pin: str = PIN,
    name: str = DISPATCHER,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    return client.post("/api/desk/login", json={"pin": pin, "name": name}, headers=headers)


def error_of(response: httpx.Response) -> str:
    return str(response.json()["error"])


def forge_cookie(key: bytes, name: str = "Mallory") -> str:
    """A session cookie built the way auth documents it, by someone who knows ``key``."""
    claims = json.dumps({"n": name, "exp": 4102444800, "sid": "00"}).encode()
    payload = base64.urlsafe_b64encode(claims).rstrip(b"=")
    mac = hmac.new(key, payload, hashlib.sha256).digest()
    return f"{payload.decode()}.{base64.urlsafe_b64encode(mac).rstrip(b'=').decode()}"


def on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def app_with_runtime(settings: Settings) -> tuple[FastAPI, FakeRuntime]:
    """The app with a stand-in runtime and no lifespan, for requests driven over ASGI."""
    app = create_app(settings, runtime_factory=Harness().factory)
    runtime = FakeRuntime(settings=settings, store=open_store(settings))
    app.state.runtime = runtime
    return app, runtime


class AsgiGet:
    """A GET driven through the ASGI interface the way uvicorn drives it (spec 2.3).

    The client stays until :meth:`hang_up`. With ``stall_after`` its socket stops draining
    after that many body chunks, so the app's next ``send`` waits, as uvicorn's does.
    """

    def __init__(self, app: FastAPI, path: str, *, stall_after: int | None = None) -> None:
        self.status = 0
        self.headers: dict[str, str] = {}
        self.body = b""
        self.answered = asyncio.Event()
        self.stalled = asyncio.Event()
        self._stall_after = stall_after
        self._chunks = 0
        self._gone = asyncio.Event()
        self._requested = False
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver"), (b"accept", b"text/event-stream")],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> dict[str, Any]:
        if not self._requested:
            self._requested = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = {name.decode(): value.decode() for name, value in message["headers"]}
        elif message.get("body"):
            if self._stall_after is not None and self._chunks >= self._stall_after:
                self.stalled.set()
                await asyncio.Event().wait()
            self._chunks += 1
            self.body += message["body"]
            self.answered.set()

    async def hang_up(self) -> None:
        self._gone.set()
        await asyncio.wait_for(self.task, timeout=5)


# --- pages, headers, read API -----------------------------------------------------------


def test_healthz_carries_security_headers(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "mode": "LIVE"}
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-cache"


def test_the_printable_document_page_is_served_for_document_and_handover_ids(
    client: TestClient,
) -> None:
    desk = client.get("/desk")
    for doc_id in ("DOC-0123456789ab", "ho_0123456789ab"):
        page = client.get(f"/docs/{doc_id}")
        assert page.status_code == 200, doc_id
        assert page.headers["content-type"].startswith("text/html")
        assert "/static/doc.js" in page.text
        assert page.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert page.headers["x-content-type-options"] == "nosniff"
        assert page.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
    assert client.get("/docs/DOC-0123456789ab").text != desk.text
    for bad in ("DOC-xyz", "ho_ABCDEF", "DOC-0123456789abcd", "adv_0123456789ab", "x"):
        assert client.get(f"/docs/{bad}").status_code == 404, bad


def test_csp_allows_no_inline_code() -> None:
    assert "'unsafe-inline'" not in CONTENT_SECURITY_POLICY
    assert "'unsafe-eval'" not in CONTENT_SECURITY_POLICY
    assert "script-src 'self' https://unpkg.com" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


def test_csp_allows_what_maplibre_and_openfreemap_need() -> None:
    """The dark style, its TileJSON, vector and raster tiles, glyphs and sprites are all on
    tiles.openfreemap.org; MapLibre 4 runs its worker from a blob: URL."""
    directives = {part.split()[0]: part.split()[1:] for part in CONTENT_SECURITY_POLICY.split("; ")}
    assert "https://unpkg.com" in directives["style-src"]
    assert "https://tiles.openfreemap.org" in directives["connect-src"]
    assert {"data:", "blob:", "https://tiles.openfreemap.org"} <= set(directives["img-src"])
    assert "blob:" in directives["worker-src"]
    assert "blob:" in directives["child-src"]


def test_csp_allows_blob_media_for_spoken_answers_and_no_new_script_host() -> None:
    directives = {part.split()[0]: part.split()[1:] for part in CONTENT_SECURITY_POLICY.split("; ")}
    assert directives["media-src"] == ["'self'", "blob:"]
    assert directives["script-src"] == [
        "'self'",
        "https://unpkg.com/maplibre-gl@4.7.1/",
        "https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/",
    ]


def test_only_the_desk_page_may_use_the_microphone(client: TestClient) -> None:
    assert client.get("/desk").headers["permissions-policy"] == (
        "camera=(), microphone=(self), geolocation=()"
    )
    closed = "camera=(), microphone=(), geolocation=()"
    for path in ("/", "/healthz", "/api/state", "/static/desk.js"):
        assert client.get(path).headers["permissions-policy"] == closed, path


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/budget", "GET"),
        ("/api/notices", "GET"),
        ("/api/recovery", "GET"),
        ("/api/docs", "GET"),
        ("/api/backtest", "GET"),
        ("/api/desk/ask", "POST"),
        ("/api/desk/ask/voice", "POST"),
        ("/api/desk/ask/speak", "POST"),
        ("/api/desk/notices", "POST"),
        ("/api/desk/recovery/run", "POST"),
        ("/api/desk/messages", "GET"),
        ("/api/desk/messages/draft", "POST"),
        ("/api/desk/handover", "POST"),
        ("/api/desk/docs/sra", "POST"),
        ("/api/desk/docs/var", "POST"),
    ],
)
def test_the_feature_routers_are_mounted_under_api(
    client: TestClient, path: str, method: str
) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    mounted = {(name, verb.upper()) for name, item in paths.items() for verb in item}
    assert (path, method) in mounted


def test_a_recording_may_be_large_but_other_bodies_stay_small(client: TestClient) -> None:
    """Only the voice route takes a body of about a megabyte; a pasted notice a few dozen
    kilobytes; anything else is refused above 16 KiB before it reaches a handler."""
    megabyte = b"x" * 1_000_000
    voice = client.post("/api/desk/ask/voice", content=megabyte)
    assert voice.status_code != 413  # passes the guard; the session check refuses it
    too_big = client.post(
        "/api/desk/ask/voice", content=b"x" * (client.app.state.settings.max_upload_bytes + 1)
    )  # type: ignore[attr-defined]
    assert too_big.status_code == 413
    notice = client.post("/api/desk/notices", content=b"x" * 30_000)
    assert notice.status_code != 413
    assert client.post("/api/desk/notices", content=b"x" * 40_000).status_code == 413
    assert client.post("/api/desk/ask", content=b"x" * 20_000).status_code == 413


@pytest.mark.parametrize("path", ["/", "/desk"])
def test_pages_are_html_with_csp(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["cache-control"] == "no-cache"


def test_pages_touch_the_disk_off_the_event_loop(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    on_loop: list[bool] = []
    is_file = Path.is_file

    def spy(path: Path) -> bool:
        on_loop.append(on_event_loop())
        return is_file(path)

    monkeypatch.setattr(Path, "is_file", spy)
    for path in ("/", "/desk"):
        assert client.get(path).status_code == 200
    assert on_loop == [False, False]


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


def test_the_guide_page_is_served_with_the_page_headers(client: TestClient) -> None:
    response = client.get("/guide")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert '<script type="module" src="/static/guide.js"></script>' in response.text


def test_airports_are_points_with_their_codes(client: TestClient) -> None:
    response = client.get("/api/airports")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"
    body = response.json()
    assert body["type"] == "FeatureCollection"
    by_icao = {f["properties"]["icao"]: f for f in body["features"]}
    assert "WIII" in by_icao
    lon, lat = by_icao["WIII"]["geometry"]["coordinates"]
    assert 106 < lon < 107
    assert -7 < lat < -6
    assert by_icao["WIII"]["properties"]["iata"] == "CGK"


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


def test_wall_lists_every_draft_of_the_mode_playing_first(
    client: TestClient, harness: Harness
) -> None:
    """In REPLAY `created_at` follows a looping clock: 60 newer advisories of an earlier run must
    not push this run's draft out of the Wall's list, and the other mode's draft is not in it."""
    harness.runtime.mode = RunMode.REPLAY
    store = harness.runtime.store
    base = make_advisory()
    later = base.created_at + timedelta(hours=3)
    mine = base.model_copy(update={"id": "adv_00000000aaaa", "replay": True})
    client.portal.call(store.put, Collection.ADVISORIES, mine.id, mine.model_dump(mode="json"))
    for n in range(60):
        old = base.model_copy(
            update={
                "id": f"adv_{n:012x}",
                "replay": True,
                "status": AdvisoryStatus.SUPERSEDED,
                "created_at": later + timedelta(minutes=n),
            }
        )
        client.portal.call(store.put, Collection.ADVISORIES, old.id, old.model_dump(mode="json"))

    listed = client.get("/api/wall").json()["advisories"]

    assert listed[0]["id"] == mine.id, "this mode's open drafts come first"
    assert ADVISORY_ID not in {a["id"] for a in listed}, "the LIVE draft is not this mode's"
    assert len(listed) == 50
    assert all(a["replay"] for a in listed)


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


def test_operator_policy_is_public_and_matches_the_state(client: TestClient) -> None:
    body = client.get("/api/policy").json()
    assert body["policy"]["policy_id"] == POLICY.policy_id
    assert body["policy"]["label"] == "ILLUSTRATIVE, not an airline SRA"
    assert body["policy"]["planner"]["level_search_ft"]["value"] == 4000
    assert body["policy_hash"] == POLICY.content_hash()
    state = client.get("/api/state").json()["policy"]
    assert (state["version"], state["policy_hash"]) == (POLICY.version, body["policy_hash"])


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


@pytest.mark.parametrize(
    "path",
    [
        "/api/blobs/frames/%2e%2e/%2e%2e/tephra.sqlite3",
        "/api/blobs/frames%2F..%2F..%2Fx.png",
        "/api/blobs/frames/..%2F..%2Fx.png",
        "/api/blobs//etc/passwd",
        "/api/blobs/%2Fetc%2Fhosts.png",
        "/api/blobs/frames\\..\\x.png",
        "/api/blobs/frames/..%5c..%5cx.png",
        "/api/blobs/frames/x.png%00.txt",
    ],
)
def test_blob_paths_cannot_leave_the_blob_store(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert error_of(response) == "not_found"
    assert response.headers["content-type"] == "application/json"


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


def test_throttle_counts_the_address_cloud_run_appended(
    settings: Settings, harness: Harness
) -> None:
    """main.run trusts every proxy, so uvicorn reports the leftmost X-Forwarded-For entry,
    which the caller writes; Cloud Run's front end appends the address it really saw."""
    app = ProxyHeadersMiddleware(
        create_app(settings, runtime_factory=harness.factory), trusted_hosts="*"
    )
    with TestClient(app) as test_client:
        for attempt in range(5):
            spoofed = {"X-Forwarded-For": f"10.9.8.{attempt}, 203.0.113.9"}
            assert login(test_client, pin="wrong-pin", headers=spoofed).status_code == 401
        blocked = login(test_client, headers={"X-Forwarded-For": "10.9.8.99, 203.0.113.9"})
        assert blocked.status_code == 429
        other = login(test_client, headers={"X-Forwarded-For": "198.51.100.20"})
        assert other.status_code == 200


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


def test_oversized_chunked_body_is_refused(client: TestClient) -> None:
    body = json.dumps({"pin": "x" * (MAX_BODY_BYTES + 1), "name": DISPATCHER}).encode()
    response = client.post(
        "/api/desk/login", content=iter([body]), headers={"Content-Type": "application/json"}
    )
    assert "content-length" not in response.request.headers
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
        # Answered before the body is read, so a half-filled form gets the same answer.
        incomplete = test_client.post("/api/desk/login", json={"pin": "", "name": "A"})
        assert (incomplete.status_code, error_of(incomplete)) == (503, "desk_disabled")
        for path in ("/api/desk/me", "/api/desk/advisories"):
            disabled = test_client.get(path)
            assert (disabled.status_code, error_of(disabled)) == (503, "desk_disabled")


@pytest.mark.parametrize("pin", ["", " "])
def test_blank_pin_disables_the_desk(settings: Settings, harness: Harness, pin: str) -> None:
    """``TEPHRA_DESK_PIN=`` (as in .env.example) parses to an empty secret, not to None."""
    app = create_app(
        settings.model_copy(update={"desk_pin": SecretStr(pin)}), runtime_factory=harness.factory
    )
    with TestClient(app) as test_client:
        response = login(test_client, pin=" ")
        assert response.status_code == 503
        assert error_of(response) == "desk_disabled"


@pytest.mark.parametrize("secret", ["", "  "])
def test_blank_session_secret_disables_the_desk(
    settings: Settings, harness: Harness, secret: str
) -> None:
    """With an empty HMAC key anyone who reads the cookie format can mint a session."""
    blank = settings.model_copy(update={"session_secret": SecretStr(secret)})
    with TestClient(create_app(blank, runtime_factory=harness.factory)) as test_client:
        test_client.cookies.set(COOKIE_NAME, forge_cookie(secret.encode()))
        me = test_client.get("/api/desk/me")
        assert me.status_code == 503
        assert error_of(me) == "desk_disabled"
        approve = test_client.post(
            f"/api/desk/advisories/{ADVISORY_ID}/approve", json={"version": 1}
        )
        assert approve.status_code == 503
        assert error_of(login(test_client)) == "desk_disabled"
    assert verify_session(forge_cookie(secret.encode()), blank, at=datetime.now(UTC)) is None


def test_logout_clears_the_cookie(client: TestClient) -> None:
    login(client)
    response = client.post("/api/desk/logout", headers={CSRF_HEADER: "1"})
    assert response.status_code == 204
    assert f"{COOKIE_NAME}=" in response.headers["set-cookie"]
    assert client.get("/api/desk/me").status_code == 401


def test_logout_refuses_cross_site_requests(client: TestClient) -> None:
    login(client)
    for headers in ({}, {"Origin": "https://evil.example", CSRF_HEADER: "1"}):
        response = client.post("/api/desk/logout", headers=headers)
        assert response.status_code == 403
        assert error_of(response) == "forbidden"
    assert client.get("/api/desk/me").status_code == 200


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


def test_desk_lists_ai_failures_and_a_dispatcher_closes_one(client: TestClient) -> None:
    assert client.get("/api/desk/ai-failures").status_code == 401
    login(client)
    listed = client.get("/api/desk/ai-failures").json()["failures"]
    assert [item["id"] for item in listed] == [FAILURE_ID]
    handled = client.post(
        f"/api/desk/ai-failures/{FAILURE_ID}/handled", json={"note": "Crew told to climb"}
    )
    assert handled.status_code == 200
    assert handled.json()["handled_by"] == f"desk:{DISPATCHER}"
    assert client.get("/api/desk/ai-failures").json() == {"failures": []}
    missing = client.post("/api/desk/ai-failures/AIF-ffffffffffff/handled", json={})
    assert missing.status_code == 404
    assert client.post("/api/desk/ai-failures/../x/handled", json={}).status_code == 404


def test_duty_lists_the_live_desks_runs_newest_first(client: TestClient) -> None:
    runs = client.get("/api/duty").json()["runs"]
    assert [run["id"] for run in runs] == ["DUTY-000000000001", "DUTY-000000000000"]
    assert client.get("/api/duty?limit=1").json()["runs"][0]["id"] == "DUTY-000000000001"
    assert client.get("/api/duty?limit=0").status_code == 422


def test_duty_lists_only_the_replay_run_playing(client: TestClient, harness: Harness) -> None:
    """Each replay run plays the recording again from its start: a run stored by an earlier
    one would sit ahead of the replay clock, so only this run's are listed."""
    runtime = harness.runtime
    runtime.mode = RunMode.REPLAY
    runtime.replay_run_since = timeutil.now() - timedelta(seconds=90)
    earlier = make_duty_runs()[2].model_copy(
        update={"id": "DUTY-00000000000e", "recorded_wall_at": timeutil.now() - timedelta(hours=3)}
    )
    client.portal.call(
        runtime.store.put, Collection.DUTY, earlier.id, earlier.model_dump(mode="json")
    )
    runs = client.get("/api/duty").json()["runs"]
    assert [run["id"] for run in runs] == ["DUTY-000000000002"]


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


def test_tick_forbidden_when_token_blank(settings: Settings, harness: Harness) -> None:
    """``TEPHRA_TASK_TOKEN=`` parses to an empty secret; an empty header must not match it."""
    app = create_app(
        settings.model_copy(update={"task_token": SecretStr("")}), runtime_factory=harness.factory
    )
    with TestClient(app) as test_client:
        response = test_client.post("/tasks/tick", headers={TASK_HEADER: ""})
        assert response.status_code == 403
        assert error_of(response) == "forbidden"
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
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert response.headers["cache-control"] == "no-cache"


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


async def test_events_endpoint_unsubscribes_when_the_client_leaves(settings: Settings) -> None:
    app, runtime = app_with_runtime(settings)
    stream = AsgiGet(app, "/api/events")
    await asyncio.wait_for(stream.answered.wait(), timeout=5)
    assert stream.status == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.body == b"retry: 3000\n\n"
    await stream.hang_up()
    assert runtime.bus.subscriber_count == 0
    assert app.state.event_streams.open == 0
    await runtime.store.aclose()


async def test_open_event_streams_are_capped(settings: Settings) -> None:
    """Each open stream holds one of Cloud Run's request slots for as long as its page is
    open. Past the cap a page is told to come back later; the pages reconnect by themselves."""
    app, runtime = app_with_runtime(settings.model_copy(update={"max_event_streams": 2}))
    held = [AsgiGet(app, "/api/events"), AsgiGet(app, "/api/stream")]
    for stream in held:
        await asyncio.wait_for(stream.answered.wait(), timeout=5)
    refused = AsgiGet(app, "/api/events")
    await asyncio.wait_for(refused.task, timeout=5)
    assert refused.status == 503
    assert json.loads(refused.body)["error"] == "too_many_streams"
    assert int(refused.headers["retry-after"]) > 0
    assert refused.headers["x-content-type-options"] == "nosniff"

    await held[0].hang_up()
    reopened = AsgiGet(app, "/api/events")
    await asyncio.wait_for(reopened.answered.wait(), timeout=5)
    assert reopened.status == 200
    for stream in (held[1], reopened):
        await stream.hang_up()
    assert app.state.event_streams.open == 0
    assert runtime.bus.subscriber_count == 0
    await runtime.store.aclose()


async def test_a_client_that_leaves_mid_send_frees_its_slot_and_subscription(
    settings: Settings,
) -> None:
    """Starlette cancels the response inside ``send`` and leaves the generator paused at its
    ``yield``, where only the garbage collector would finish it."""
    app, runtime = app_with_runtime(settings)
    stream = AsgiGet(app, "/api/events", stall_after=1)
    await asyncio.wait_for(stream.answered.wait(), timeout=5)
    runtime.bus.publish(SseEvent.TRACE, {"n": 1})
    await asyncio.wait_for(stream.stalled.wait(), timeout=5)
    await stream.hang_up()
    assert app.state.event_streams.open == 0
    assert runtime.bus.subscriber_count == 0
    await runtime.store.aclose()


async def test_a_client_that_falls_behind_is_closed_and_resumes_from_history() -> None:
    """Publishers never wait for a slow client. Once its queue has dropped events the stream
    ends, the browser reconnects with the last id it saw, and the bus history fills the gap."""
    bus = EventBus()
    stream = event_stream(bus, heartbeat_s=5.0)
    assert await anext(stream) == "retry: 3000\n\n"
    seen = bus.publish(SseEvent.TRACE, {"n": -1})
    assert (await anext(stream)).startswith(f"id: {seen.id}\n")
    missed = [
        bus.publish(name, {"n": n}) for n in range(150) for name in (SseEvent.TRACE, SseEvent.STATE)
    ]
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    assert bus.subscriber_count == 0

    resumed = event_stream(bus, heartbeat_s=5.0, last_event_id=seen.id)
    assert await anext(resumed) == "retry: 3000\n\n"
    replayed = [await anext(resumed) for _ in missed]
    assert [frame.split("\n", 1)[0] for frame in replayed] == [f"id: {e.id}" for e in missed]
    await resumed.aclose()


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
