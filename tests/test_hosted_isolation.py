"""Isolation between hosted airlines, and between them and the demo (SPEC §6.3, tests 1-22),
through the HTTP layer over the real hosted domain and runtimes: two airlines, RFB (SHADOW)
and RFC (LIVE), beside the demo, on the stub model and SQLite.

Where a numbered item is proven at another layer too (the domain's own tests, H2's runtime
tests), the test here checks what the HTTP layer adds; each test names its item.
"""

import asyncio
import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from tephra.airline import accounts, passwords
from tephra.airline.models import AirlineLogin
from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.api import server
from tephra.api.auth import CSRF_HEADER, TASK_HEADER, wall_clock_now
from tephra.api.tenancy import ROUTE_INDEX, TENANT_ROUTES, tenant_scope
from tephra.hosted import keys, members, tenants
from tephra.hosted.models import Member, TenantAssistant
from tephra.hosted.settings_for import tenant_settings
from tephra.models import AuditAction, CrewCue
from tephra.pipeline import create_runtime
from tephra.store.base import Collection
from tephra.util import timeutil
from tests.test_hosted_api import (
    GEMINI_KEY,
    PASSWORD,
    TASK_TOKEN,
    Holder,
    HostedSite,
    as_login,
    error_of,
    httpx_push,
    position,
)
from tests.test_pipeline import AT

_PARAM = re.compile(r"\{[^}]+\}")
KEY_RFC = "AIzaRFC-test-key-0123456789abcdefghijklmn"
OPERATOR_EMAIL = "m.tan@tephra.example"


@dataclass
class Two:
    """RFB in SHADOW (Ana ops manager, Dee dispatcher, Vic viewer), RFC in LIVE (Ola ops
    manager), and Sam, a login that belongs to no airline."""

    rfb: Holder
    ana: Member
    dee: AirlineLogin
    dee_member: Member
    vic: AirlineLogin
    vic_member: Member
    rfc: Holder
    ola: Member
    sam: AirlineLogin
    rfb_key: str
    rfc_key: str


async def _build(site: HostedSite) -> Two:
    rfb, ana = await site.airline("RFB", "shadow")
    dee, dee_member = await site.person("RFB", "dispatcher", "dee@rfb.example", "Dee D", by=ana)
    vic, vic_member = await site.person("RFB", "viewer", "vic@rfb.example", "Vic V", by=ana)
    rfc, ola = await site.airline("RFC", "live")
    sam = await accounts.create_member_login(
        site.root,
        email="sam@nowhere.example",
        password_hash=await passwords.hashed(PASSWORD),
        recovery_sha256="0" * 64,
        at=wall_clock_now(),
    )
    _, rfb_key = await site.reg.create_key("RFB", "Ops", by=tenants.member_by(ana))
    _, rfc_key = await site.reg.create_key("RFC", "Ops", by=tenants.member_by(ola))
    return Two(rfb, ana, dee, dee_member, vic, vic_member, rfc, ola, sam, rfb_key, rfc_key)


@pytest.fixture(autouse=True)
def _no_startup_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    async def skip(runtime: Any) -> None:
        return None

    monkeypatch.setattr(server, "_startup_tick", skip)


@pytest.fixture
def site(tmp_path: Path) -> HostedSite:
    return HostedSite(tmp_path)


@pytest.fixture
def client(site: HostedSite) -> Iterator[TestClient]:
    with TestClient(site.app, follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def stub_models(site: HostedSite) -> None:
    """RFB's runtime on the stub model, so a tick drafts offline. A hosted airline never gets
    the stub in the product (no key: AI UNAVAILABLE); this swaps the test's factory only."""

    async def factory(settings: Any, *, hosted: Any) -> Any:
        if hosted.tenant != "RFB":  # RFC goes live: a reconfigure keeps the backend kind
            return await create_runtime(settings, hosted=hosted)
        stubbed = settings.model_copy(update={"llm": "stub", "gemini_api_key": None})
        return await create_runtime(stubbed, hosted=replace(hosted, llm_unavailable=None))

    site.factory = factory


@pytest.fixture
def two(client: TestClient, site: HostedSite) -> Two:
    return site.run(client, lambda: _build(site))


def concrete(template: str) -> str:
    values = {
        "{advisory_id}": "adv_0123456789ab",
        "{message_id}": "msg_0123456789ab",
        "{doc_id}": "DOC-0123456789ab",
        "{handover_id}": "ho_0123456789ab",
        "{report_id}": "CR-0123456789",
        "{failure_id}": "AIF-0123456789ab",
        "{connection_id}": "CN-0123456789",
        "{invite_id}": "IV-0123456789",
        "{member_id}": "MB-0123456789",
        "{origin_icao}": "WIII",
        "{dest_icao}": "WADD",
    }
    for name, value in values.items():
        template = template.replace(name, value)
    return _PARAM.sub("x", template)


def call(client: TestClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
    headers = {CSRF_HEADER: "1", **kwargs.pop("headers", {})}
    return client.request(method, path, json=kwargs.pop("json", {}), headers=headers, **kwargs)


def member_routes() -> list[tuple[str, str]]:
    return sorted(key for key, rule in TENANT_ROUTES.items() if rule.need != "key")


def live_routes() -> list[tuple[str, str]]:
    """The airline routes that hold a stream open: called with a short read instead."""
    return [("GET", "/api/events"), ("GET", "/api/stream")]


def safe(method: str, path: str) -> bool:
    return (method, path) not in live_routes()


# --- 1. the route inventory -------------------------------------------------------------


def test_1_every_route_is_checked_and_the_table_is_real(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    inventory = []
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute):
            path = str(context.path_format)
            if path.startswith(("/api/", "/tasks/")):
                deps = list(context.dependencies)
                assert any(d.dependency is tenant_scope for d in deps), path
                inventory.append((next(iter(context.methods)), path))
    assert set(TENANT_ROUTES) <= set(ROUTE_INDEX.values())
    as_login(client, site, two.rfb.login, two.rfb.record)
    for method, path in inventory:
        if (method, path) in TENANT_ROUTES or path.startswith("/tasks/"):
            continue
        answered = call(client, method, "/a/RFB" + concrete(path))
        assert (answered.status_code, error_of(answered)) == (404, "not_hosted"), path


# --- 2. who may call at all ---------------------------------------------------------------


def test_2_strangers_get_401_or_the_same_404_on_every_route(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    for method, path in member_routes():
        target = concrete(path)
        client.cookies.clear()
        assert call(client, method, "/a/RFB" + target).status_code == 401, path
        as_login(client, site, two.rfc.login, two.rfc.record)
        other = call(client, method, "/a/RFB" + target)
        as_login(client, site, two.sam)
        nobody = call(client, method, "/a/RFB" + target)
        missing = call(client, method, "/a/RFZ" + target)
        for answered in (other, nobody, missing):
            assert answered.status_code == 404, (path, answered.text)
            assert answered.json() == {
                "error": "no_such_airline",
                "detail": "No such airline",
                "problems": [],
                "current": None,
            }, path


def test_2_every_bad_push_is_the_same_401_and_reads_nothing(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    meter = cast(FastAPI, client.app).state.meter
    site.run(client, lambda: _suspend(site, "RFC"))
    before = meter.day().model_dump()
    client.cookies.clear()
    answers_seen = [
        httpx_push(client, "RFZ", two.rfb_key, positions=[position()]),
        httpx_push(client, "RFC", two.rfc_key, positions=[position()]),
        httpx_push(client, "RFB", None, positions=[position()]),
        httpx_push(client, "RFB", "tph_" + "x" * 32, positions=[position()]),
        httpx_push(client, "RFB", two.rfc_key, positions=[position()]),
    ]
    bodies = {(a.status_code, a.text) for a in answers_seen}
    assert len(bodies) == 1
    assert next(iter(bodies))[0] == 401
    assert error_of(answers_seen[0]) == "bad_key"
    assert meter.day().model_dump() == before


async def _suspend(site: HostedSite, icao: str) -> None:
    space = site.reg.space(icao)
    await tenants.suspend(
        site.root,
        icao,
        by="operator:M. Tan#4f1c2a9b",
        reason="test",
        space=space,
        at=wall_clock_now(),
    )
    await site.reg.stop(icao, reason="test")


def test_2_bad_keys_from_one_client_are_throttled(client: TestClient, two: Two) -> None:
    for _ in range(10):
        assert (
            httpx_push(client, "RFB", "tph_" + "y" * 32, positions=[position()]).status_code == 401
        )
    blocked = httpx_push(client, "RFB", two.rfb_key, positions=[position()])
    assert (blocked.status_code, error_of(blocked)) == (429, "too_many_attempts")


# --- 3. roles ---------------------------------------------------------------------------


def test_3_a_viewer_and_a_dispatcher_are_refused_what_their_role_cannot_do(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    for login, refused_needs in (
        (two.vic, {"dispatcher", "ops_manager"}),
        (two.dee, {"ops_manager"}),
    ):
        as_login(client, site, login)
        for (method, path), rule in sorted(TENANT_ROUTES.items()):
            if rule.need not in refused_needs or "shadow" not in rule.states:
                continue
            answered = call(client, method, "/a/RFB" + concrete(path))
            assert (answered.status_code, error_of(answered)) == (403, "role"), (
                path,
                answered.text,
            )


# --- 4. object ids across airlines --------------------------------------------------------


def test_4_one_airline_s_ids_mean_nothing_under_another(
    stub_models: None, client: TestClient, site: HostedSite, two: Two
) -> None:
    rfb = site.reg.handle("RFB")
    assert rfb is not None
    runtime = rfb.runtime
    assert runtime is not None

    async def draft() -> None:
        await _drafts(runtime)

    site.run(client, draft)
    as_login(client, site, two.rfb.login, two.rfb.record)
    advisories = client.get("/a/RFB/api/desk/advisories").json()["advisories"]
    assert advisories, "the fixture flight RFB417 is exposed: RFB has drafts"
    advisory = advisories[0]
    report = call(
        client,
        "POST",
        "/a/RFB/api/desk/crew-reports",
        json={
            "callsign": "RFB417",
            "cues": [CrewCue.SULPHUR_SMELL.value],
            "lat": -8.1,
            "lon": 113.0,
            "level_from_fl": 120,
            "observed_at": timeutil.to_iso(wall_clock_now()),
        },
    )
    assert report.status_code == 200, report.text
    keys_listed = client.get("/a/RFB/api/tenant/keys").json()["keys"]
    invite = call(
        client,
        "POST",
        "/a/RFB/api/tenant/people/invites",
        json={"email": "z@rfb.example", "role": "viewer"},
    ).json()["invite"]
    ids = {
        "advisory": f"/api/desk/advisories/{advisory['id']}/approve",
        "connection": f"/api/tenant/keys/{keys_listed[0]['id']}/revoke",
        "invite": f"/api/tenant/people/invites/{invite['id']}/revoke",
        "member": f"/api/tenant/people/{two.dee_member.id}/remove",
        "chain": f"/api/advisories/{advisory['id']}/chain",
    }
    ids["crew report"] = f"/api/desk/crew-reports/{report.json()['report']['id']}/withdraw"
    as_login(client, site, two.rfc.login, two.rfc.record)
    for what, path in ids.items():
        method = "GET" if path.endswith("/chain") else "POST"
        answered = call(
            client,
            method,
            "/a/RFC" + path,
            json={"version": advisory["version"], "reason": "x" * 5},
        )
        assert answered.status_code == 404, (what, answered.text)
    assert error_of(httpx_push(client, "RFC", two.rfb_key, positions=[position()])) == "bad_key"


async def _drafts(runtime: Any) -> None:
    """One tick and its AI work on the fixture feeds, which are current at the fixture's own
    time: the airline's runtime is given that time as its wall clock (as H2's tests do)."""
    runtime.wall_clock = timeutil.FixedClock(AT)
    await runtime.tick(reason="manual")
    with runtime.bound():
        await runtime.worker.drain()


# --- 5. the demo and the airlines never mix -------------------------------------------------


def test_5_the_demo_and_an_airline_never_list_each_other_s_documents(
    stub_models: None, client: TestClient, site: HostedSite, two: Two
) -> None:
    rfb = site.reg.handle("RFB")
    assert rfb is not None
    assert rfb.runtime is not None

    async def tick_both() -> None:
        assert site.demo is not None
        await site.demo.tick(reason="manual")
        await site.demo.worker.drain()
        await _drafts(rfb.runtime)

    site.run(client, tick_both)
    as_login(client, site, two.rfb.login, two.rfb.record)
    for path in ("/api/advisories", "/api/audit", "/api/outbound", "/api/duty", "/api/docs"):
        tenant = client.get("/a/RFB" + path)
        client.cookies.clear()
        demo = client.get(path)
        as_login(client, site, two.rfb.login, two.rfb.record)
        assert tenant.status_code == 200, (path, tenant.text)
        assert demo.status_code == 200, (path, demo.text)
        tenant_ids = set(re.findall(r'"id":"([^"]+)"', tenant.text))
        demo_ids = set(re.findall(r'"id":"([^"]+)"', demo.text))
        assert not tenant_ids & demo_ids, path
    demo_actions = {
        entry["action"] for entry in client.get("/api/audit?limit=200").json()["entries"]
    }
    hosted = {
        a.value for a in AuditAction if a.value.startswith(("HOSTED_", "MEMBER_", "MODEL_KEY"))
    }
    assert not demo_actions & hosted
    tenant_flights = {
        a["callsign"] for a in client.get("/a/RFB/api/advisories").json()["advisories"]
    }
    assert tenant_flights <= {"RFB417"}


# --- 6. event streams -------------------------------------------------------------------


class Stream:
    """An event stream driven over ASGI as uvicorn drives it, with a cookie."""

    def __init__(self, app: FastAPI, path: str, cookie: str | None = None) -> None:
        self.status = 0
        self.body = b""
        self.started = asyncio.Event()
        self.ended = asyncio.Event()
        self._gone = asyncio.Event()
        self._asked = False
        headers = [(b"host", b"testserver"), (b"accept", b"text/event-stream")]
        if cookie is not None:
            headers.append((b"cookie", f"{AIRLINE_COOKIE}={cookie}".encode()))
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
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
        }
        self.task = asyncio.create_task(self._run(app, scope))

    async def _run(self, app: FastAPI, scope: dict[str, Any]) -> None:
        try:
            await app(scope, self._receive, self._send)
        finally:
            self.ended.set()

    async def _receive(self) -> dict[str, Any]:
        if not self._asked:
            self._asked = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message.get("body"):
            self.body += message["body"]
        self.started.set()

    async def hang_up(self) -> None:
        self._gone.set()
        await asyncio.wait_for(self.task, timeout=5)


def test_6_streams_stay_inside_their_airline_and_end_when_access_ends(
    client: TestClient, site: HostedSite, two: Two, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server, "TENANT_STREAM_CHECK_S", 0.05)
    app = cast(FastAPI, client.app)
    dee = site.cookie(two.dee)
    ola = site.cookie(two.rfc.login, two.rfc.record)

    async def scenario() -> None:
        rfb_stream = Stream(app, "/a/RFB/api/events", dee)
        rfc_stream = Stream(app, "/a/RFC/api/events", ola)
        demo_stream = Stream(app, "/api/events")
        for stream in (rfb_stream, rfc_stream, demo_stream):
            await asyncio.wait_for(stream.started.wait(), 5)
            assert stream.status == 200
        rfb = site.reg.handle("RFB")
        assert rfb is not None
        assert rfb.runtime is not None
        rfb.runtime.bus.publish("trace", {"marker": "only-for-rfb"})
        await asyncio.sleep(0.2)
        assert b"only-for-rfb" in rfb_stream.body
        assert b"only-for-rfb" not in rfc_stream.body + demo_stream.body
        # a removed member's open stream ends within the check interval
        await members.remove(
            site.root,
            "RFB",
            two.dee_member.id,
            by=two.ana,
            space=rfb.space,
            access=site.reg.access,
            at=wall_clock_now(),
        )
        await asyncio.wait_for(rfb_stream.ended.wait(), 5)
        # a suspended airline's streams end
        await _suspend(site, "RFC")
        await asyncio.wait_for(rfc_stream.ended.wait(), 5)
        assert not demo_stream.ended.is_set()
        await demo_stream.hang_up()

    site.run(client, scenario)


def test_6_the_eleventh_stream_of_an_airline_is_refused_and_the_demo_s_still_open(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    vic, dee = site.cookie(two.vic), site.cookie(two.dee)
    ana = site.cookie(two.rfb.login, two.rfb.record)

    async def scenario() -> None:
        held = [Stream(app, "/a/RFB/api/events", who) for who in [vic] * 4 + [dee] * 4]
        held += [Stream(app, "/a/RFB/api/events", ana) for _ in range(2)]
        for stream in held:
            await asyncio.wait_for(stream.started.wait(), 5)
            assert stream.status == 200
        eleventh = Stream(app, "/a/RFB/api/events", ana)
        await asyncio.wait_for(eleventh.ended.wait(), 5)
        assert eleventh.status == 503
        assert b"too_many_streams" in eleventh.body
        demo = Stream(app, "/api/events")
        await asyncio.wait_for(demo.started.wait(), 5)
        assert demo.status == 200
        for stream in [*held, demo]:
            await stream.hang_up()
        assert cast(FastAPI, app).state.tenant_streams["RFB"].open == 0

    site.run(client, scenario)


def test_6_one_member_holds_at_most_four_of_the_airline_s_streams(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    vic, dee = site.cookie(two.vic), site.cookie(two.dee)

    async def scenario() -> None:
        held = [Stream(app, "/a/RFB/api/events", vic) for _ in range(4)]
        for stream in held:
            await asyncio.wait_for(stream.started.wait(), 5)
            assert stream.status == 200
        fifth = Stream(app, "/a/RFB/api/events", vic)
        await asyncio.wait_for(fifth.ended.wait(), 5)
        assert (fifth.status, b"too_many_streams" in fifth.body) == (503, True)
        other = Stream(app, "/a/RFB/api/events", dee)  # another member of RFB still opens
        await asyncio.wait_for(other.started.wait(), 5)
        assert other.status == 200
        for stream in [*held, other]:
            await stream.hang_up()

    site.run(client, scenario)


def test_6_demo_visitors_filling_every_demo_place_never_cut_an_airline_off(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    """The demo's streams have their own places (max_event_streams less every airline's)."""
    app = cast(FastAPI, client.app)
    demo_places = app.state.event_streams.limit
    assert demo_places == (
        site.settings.max_event_streams
        - site.settings.hosted_max_tenants * site.settings.hosted_streams_per_tenant
    )
    app.state.event_streams.open = demo_places  # every demo place taken by visitors
    vic = site.cookie(two.vic)

    async def scenario() -> None:
        visitor = Stream(app, "/api/events")
        await asyncio.wait_for(visitor.ended.wait(), 5)
        assert visitor.status == 503
        member = Stream(app, "/a/RFB/api/events", vic)
        await asyncio.wait_for(member.started.wait(), 5)
        assert member.status == 200
        await member.hang_up()

    try:
        site.run(client, scenario)
    finally:
        app.state.event_streams.open = 0


# --- 7. wall clock while the demo replays ----------------------------------------------------


def test_7_airline_work_runs_on_the_wall_clock_while_the_demo_replays(
    client: TestClient, site: HostedSite
) -> None:
    replay = datetime(2020, 1, 1, tzinfo=UTC)
    with timeutil.use_clock(timeutil.FixedClock(replay)):
        two = site.run(client, lambda: _build(site))
        as_login(client, site, two.rfb.login, two.rfb.record)
        tenant_now = datetime.fromisoformat(client.get("/a/RFB/api/state").json()["now"])
        client.cookies.clear()
        demo_now = datetime.fromisoformat(client.get("/api/state").json()["now"])
        assert demo_now == replay
        assert abs((tenant_now - wall_clock_now()).total_seconds()) < 5

        site.run(client, site.reg.run_pass)
        rfb = site.reg.handle("RFB")
        assert rfb is not None
        assert rfb.health.last_tick_wall_at is not None
        assert abs((rfb.health.last_tick_wall_at - wall_clock_now()).total_seconds()) < 30
        entries = _entries(site, client, "RFB")
        assert {AuditAction.HOSTED_SETUP.value, AuditAction.MEMBER_JOINED.value} <= {
            e["action"] for e in entries
        }
        for entry in entries:
            at = datetime.fromisoformat(entry["at"])
            assert abs((at - wall_clock_now()).total_seconds()) < 60, entry["action"]
        as_login(client, site, two.rfb.login, two.rfb.record)
        invite = call(
            client,
            "POST",
            "/a/RFB/api/tenant/people/invites",
            json={"email": "n@rfb.example", "role": "viewer"},
        ).json()["invite"]
        expires = datetime.fromisoformat(invite["expires_at"])
        assert abs((expires - wall_clock_now() - timedelta(hours=72)).total_seconds()) < 5
        with timeutil.bind_clock(timeutil.SystemClock()), pytest.raises(RuntimeError):
            timeutil.set_clock(timeutil.SystemClock())
        rfb_store = rfb.space.store
        with pytest.raises(RuntimeError, match="outside its binding"):
            site.run(client, lambda: rfb_store.get(Collection.AUDIT, "1"))


def _entries(site: HostedSite, client: TestClient, icao: str) -> list[dict[str, Any]]:
    space = site.reg.space(icao)

    async def read() -> list[dict[str, Any]]:
        with space.bound():
            return await space.store.list_docs(
                Collection.AUDIT, limit=500, order_by="seq", descending=False
            )

    return site.run(client, read)


# --- 8. keys ------------------------------------------------------------------------------


def test_8_no_key_reaches_the_environment_a_body_a_log_or_another_airline(
    client: TestClient, site: HostedSite, two: Two, caplog: pytest.LogCaptureFixture
) -> None:
    import os

    caplog.set_level(logging.DEBUG)
    assert "GOOGLE_API_KEY" not in os.environ
    assert "GEMINI_API_KEY" not in os.environ
    seen: list[bytes] = []
    as_login(client, site, two.rfb.login, two.rfb.record)
    for icao, holder, key in (("RFB", two.rfb, GEMINI_KEY), ("RFC", two.rfc, KEY_RFC)):
        as_login(client, site, holder.login, holder.record)
        answered = client.put(f"/a/{icao}/api/tenant/assistant/key", json={"key": key})
        assert answered.status_code == 200, answered.text
        seen.append(answered.content)
        for path in ("/api/tenant/assistant", "/api/tenant/header", "/api/state", "/api/budget"):
            seen.append(client.get(f"/a/{icao}{path}").content)
    rfb = site.reg.handle("RFB")
    rfc = site.reg.handle("RFC")
    assert rfb is not None
    assert rfc is not None
    assert rfb.runtime is not None
    assert rfc.runtime is not None
    assert rfb.runtime.settings.gemini_api_key.get_secret_value() == GEMINI_KEY  # type: ignore[union-attr]
    assert rfc.runtime.settings.gemini_api_key.get_secret_value() == KEY_RFC  # type: ignore[union-attr]
    for key in (GEMINI_KEY, KEY_RFC):
        for body in seen:
            assert key[:8].encode() not in body
        assert key[:8] not in caplog.text
        assert key not in repr(rfb.runtime.settings) + repr(rfc.runtime.settings)
    copied = rfb.record.model_key
    assert copied is not None
    with pytest.raises(keys.KeyUnreadable):
        keys.unseal("RFC", copied, site.settings)
    record = site.run(client, lambda: accounts.get_record(site.root, two.rfb.record.id))
    built = tenant_settings(site.settings, rfb.record, record.submitted(), None)
    assert (built.task_token, built.key_secret, built.desk_pin) == (None, None, None)


# --- 9, 10. path tricks and cross-site requests ----------------------------------------------


@pytest.mark.parametrize(
    "path", ["/a/rfb/api/state", "/a/RFBX/api/state", "/a/RFB//api/state", "/a/RFB/api/%2e%2e/mode"]
)
def test_9_tricky_paths_are_404(client: TestClient, site: HostedSite, two: Two, path: str) -> None:
    as_login(client, site, two.rfb.login, two.rfb.record)
    assert client.get(path).status_code == 404


def test_10_cross_site_writes_are_refused_on_airline_and_operator_routes(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    as_login(client, site, two.rfb.login, two.rfb.record)
    for path in ("/a/RFB/api/tenant/keys", "/api/admin/sign-in", "/api/hosted/invites/lookup"):
        cross = client.post(path, json={"name": "x"}, headers={"sec-fetch-site": "cross-site"})
        foreign = client.post(path, json={"name": "x"}, headers={"origin": "https://evil.example"})
        form = client.post(
            path, content=b"name=x", headers={"content-type": "application/x-www-form-urlencoded"}
        )
        for answered in (cross, foreign, form):
            assert answered.status_code == 403, (path, answered.text)


# --- 11. states ---------------------------------------------------------------------------


def test_11_suspended_reads_setup_has_not_started_and_deleted_is_gone(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    site.run(client, lambda: _suspend(site, "RFB"))
    as_login(client, site, two.rfb.login, two.rfb.record)
    for (method, path), rule in sorted(TENANT_ROUTES.items()):
        if not path.startswith("/api/tenant/"):
            continue
        answered = call(client, method, "/a/RFB" + concrete(path))
        if method == "GET":
            assert answered.status_code == 200, (path, answered.text)
        elif "suspended" not in rule.states:
            assert (answered.status_code, error_of(answered)) == (403, "tenant_suspended"), path
    holder, _ = site.run(client, lambda: site.airline("RFD", "setup"))
    as_login(client, site, holder.login, holder.record)
    for (method, path), rule in sorted(TENANT_ROUTES.items()):
        if (
            rule.states == frozenset({"shadow", "live"})
            and rule.need != "key"
            and safe(method, path)
        ):
            answered = call(client, method, "/a/RFD" + concrete(path))
            assert (answered.status_code, error_of(answered)) == (409, "not_started"), path


# --- 12. places ---------------------------------------------------------------------------


async def _ready(site: HostedSite, icao: str) -> Holder:
    """An airline in setup with its checklist done: model and key, policy confirmed, a
    dispatcher, and positions pushed on a live key in the last minutes."""
    holder, ana = await site.airline(icao, "setup")
    space = site.reg.space(icao)
    by, at = tenants.member_by(ana), wall_clock_now()
    assistant = TenantAssistant(model="gemini-3.8-flash", model_lite="gemini-3.5-flash-lite")
    await tenants.set_assistant(
        site.root, icao, assistant, by=by, settings=site.settings, space=space, at=at
    )
    sealed = keys.seal(icao, GEMINI_KEY, site.settings, by=by, at=at)
    await tenants.set_key(site.root, icao, sealed, by=by, space=space, at=at)
    await tenants.confirm_policy(site.root, icao, version=1, by=by, space=space, at=at)
    await site.person(icao, "dispatcher", f"dee@{icao.lower()}.example", "Dee D", by=ana)
    made, _ = await site.reg.create_key(icao, "Ops", by=by)
    space.feed_stats.record(
        accepted={"positions": 1}, refused=[], wall_at=at, connection_id=made.id
    )
    await site.reg.reload(icao)
    return holder


def test_12_four_starts_for_three_places_and_stop_frees_one(
    client: TestClient, site: HostedSite
) -> None:
    app = cast(FastAPI, client.app)
    holders = {
        icao: site.run(client, lambda icao=icao: _ready(site, icao))
        for icao in ("RFB", "RFC", "RFD", "RFE")
    }
    cookies = {icao: site.cookie(h.login, h.record) for icao, h in holders.items()}

    async def race() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await asyncio.gather(
                *(
                    ac.post(
                        f"/a/{icao}/api/tenant/start",
                        json={"region": "java_bali"},
                        headers={"cookie": f"{AIRLINE_COOKIE}={cookies[icao]}"},
                    )
                    for icao in holders
                )
            )

    answered = site.run(client, race)
    statuses = sorted(a.status_code for a in answered)
    assert statuses == [200, 200, 200, 409], [a.text for a in answered]
    loser = next(a for a in answered if a.status_code == 409)
    assert error_of(loser) in {"airline_limit_reached", "checklist_open"}
    started = [icao for icao, a in zip(holders, answered, strict=True) if a.status_code == 200]
    as_login(client, site, holders[started[0]].login, holders[started[0]].record)
    stop = client.post(f"/a/{started[0]}/api/tenant/stop", json={"reason": "Make room"})
    assert stop.status_code == 200, stop.text
    waiting = next(icao for icao in holders if icao not in started)
    as_login(client, site, holders[waiting].login, holders[waiting].record)
    assert (
        client.post(f"/a/{waiting}/api/tenant/start", json={"region": "java_bali"}).status_code
        == 200
    )


# --- 13. access changes take effect on the next request ---------------------------------------


def test_13_removal_role_change_and_sign_out_everywhere_act_on_the_next_request(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    as_login(client, site, two.dee)
    assert client.get("/a/RFB/api/desk/me").json()["role"] == "dispatcher"
    as_login(client, site, two.rfb.login, two.rfb.record)
    call(
        client,
        "POST",
        f"/a/RFB/api/tenant/people/{two.dee_member.id}/role",
        json={"role": "viewer"},
    )
    as_login(client, site, two.dee)
    assert client.get("/a/RFB/api/desk/me").json()["role"] == "viewer"
    approve = call(
        client, "POST", "/a/RFB/api/desk/advisories/adv_0123456789ab/approve", json={"version": 1}
    )
    assert error_of(approve) == "role"
    as_login(client, site, two.vic)
    held = site.cookie(two.vic)
    assert client.post("/api/airline/sign-out", json={}).status_code == 204
    client.cookies.set(AIRLINE_COOKIE, held)
    assert client.get("/a/RFB/api/desk/me").status_code == 404
    as_login(client, site, two.rfb.login, two.rfb.record)
    call(client, "POST", f"/a/RFB/api/tenant/people/{two.dee_member.id}/remove")
    as_login(client, site, two.dee)
    assert error_of(client.get("/a/RFB/api/desk/me")) == "no_such_airline"


# --- 14, 15. failures and pauses stay with their airline --------------------------------------


def test_14_an_airline_whose_ticks_fail_never_stops_the_others(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    rfb, rfc = site.reg.handle("RFB"), site.reg.handle("RFC")
    assert rfb is not None
    assert rfc is not None
    assert rfb.runtime is not None

    async def broken(*, reason: str = "hosted") -> Any:
        raise RuntimeError("feed parser exploded")

    rfb.runtime.tick = broken  # type: ignore[method-assign]
    for _ in range(3):
        site.run(client, site.reg.run_pass)
    assert rfc.health.last_tick_wall_at is not None
    assert rfc.health.failures == 0
    as_login(client, site, two.rfb.login, two.rfb.record)
    header = client.get("/a/RFB/api/tenant/header").json()
    assert header["runtime"]["failures"] >= 3 or header["runtime"]["problem"]
    client.cookies.clear()
    assert client.get("/api/state").status_code == 200


def test_14_an_airline_that_cannot_start_leaves_the_site_serving(
    client: TestClient, site: HostedSite
) -> None:
    async def refuse(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    site.factory = refuse
    holder, _ = site.run(client, lambda: site.airline("RFB", "shadow"))
    as_login(client, site, holder.login, holder.record)
    header = client.get("/a/RFB/api/tenant/header").json()
    assert header["runtime"]["running"] is False
    assert "could not start" in header["runtime"]["problem"]
    assert error_of(client.get("/a/RFB/api/state")) == "not_started"
    client.cookies.clear()
    assert client.get("/api/state").status_code == 200


def test_15_an_airline_over_its_allowance_pauses_alone(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    meter = cast(FastAPI, client.app).state.meter
    meter.count("RFB", "writes", 3_200)
    site.run(client, site.reg.run_pass)
    rfb, rfc = site.reg.handle("RFB"), site.reg.handle("RFC")
    assert rfb is not None
    assert rfc is not None
    assert (rfb.health.paused, rfb.health.paused_scope) == ("writes", "airline")
    assert rfc.health.paused is None
    assert rfc.health.last_tick_wall_at is not None
    paused = httpx_push(client, "RFB", two.rfb_key, positions=[position()])
    assert (paused.status_code, error_of(paused)) == (503, "airline_paused")
    as_login(client, site, two.rfb.login, two.rfb.record)
    assert client.get("/a/RFB/api/tenant/header").json()["paused"]["scope"] == "airline"
    meter.count("demo", "writes", 16_000)  # the demo's own use never pauses an airline
    site.run(client, site.reg.run_pass)
    assert rfc.health.paused is None
    meter.count("RFC", "writes", 12_800)  # the airlines together reach the site's cap
    site.run(client, site.reg.run_pass)
    assert rfc.health.paused_scope == "site"
    client.cookies.clear()
    site_paused = httpx_push(client, "RFC", two.rfc_key, positions=[position()])
    assert (site_paused.status_code, error_of(site_paused)) == (503, "site_paused")


def test_15_a_member_s_reads_are_their_airline_s_and_stop_at_its_ceiling(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    """What a member's request reads in the root store (people, logins, the record) is that
    airline's use, never the demo's; past the airline's ceiling its reads answer 503 while
    the header still says why, and the demo and RFC keep answering (H1)."""
    meter = cast(FastAPI, client.app).state.meter
    as_login(client, site, two.rfb.login, two.rfb.record)
    assert client.get("/a/RFB/api/tenant/people").status_code == 200  # warms the access cache
    before = meter.day()
    assert client.get("/a/RFB/api/tenant/people").status_code == 200
    after = meter.day()
    assert after.reads.get("demo", 0) == before.reads.get("demo", 0)
    assert after.reads.get("RFB", 0) > before.reads.get("RFB", 0)
    meter.count("RFB", "reads", meter.ceiling(site.settings))
    refused = client.get("/a/RFB/api/tenant/people")
    assert (refused.status_code, error_of(refused)) == (503, "airline_paused")
    assert client.get("/a/RFB/api/tenant/header").status_code == 200
    as_login(client, site, two.rfc.login, two.rfc.record)
    assert client.get("/a/RFC/api/tenant/people").status_code == 200
    client.cookies.clear()
    assert client.get("/api/audit").status_code == 200


def test_15_the_demo_s_visitors_reading_past_the_cap_pause_no_airline(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    meter = cast(FastAPI, client.app).state.meter
    meter.count("demo", "reads", site.settings.hosted_reads_cap * 2)
    site.run(client, site.reg.run_pass)
    for icao in ("RFB", "RFC"):
        handle = site.reg.handle(icao)
        assert handle is not None
        assert handle.health.paused is None
    pushed = httpx_push(client, "RFC", two.rfc_key, positions=[position()])
    assert pushed.status_code == 200, pushed.text


def test_2_one_account_spending_the_site_wide_request_count_locks_no_member_out(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    """The onboarding's site-wide signed-in request count (5,000 a day) is not used with
    hosting on: a self-made account spending it once locked every airline's people out (H2)."""
    state = cast(FastAPI, client.app).state
    while not state.airline_requests_all.blocked("site"):
        state.airline_requests_all.record_failure("site")
    site.reg.access.drop()  # every member's access entry cold
    as_login(client, site, two.dee)
    assert client.get("/a/RFB/api/tenant/header").status_code == 200
    assert client.get("/api/hosted/me").status_code == 200
    as_login(client, site, two.rfb.login, two.rfb.record)
    assert client.get("/api/airline/me").status_code == 200


# --- 16, 17. operators; no tokens in paths, no emails in records ------------------------------


def test_16_the_console_is_for_operators_only(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    as_login(client, site, two.rfb.login, two.rfb.record)
    assert client.get("/api/admin/airlines").status_code in {401, 403}
    client.cookies.clear()
    assert client.get("/api/admin/airlines").status_code == 401
    minted = client.post(
        "/tasks/operator-invite",
        json={"name": "M. Tan", "email": OPERATOR_EMAIL},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    token = minted.json()["link"].split("#", 1)[1]
    client.post(
        "/api/admin/invite/accept",
        json={"token": token, "email": OPERATOR_EMAIL, "password": PASSWORD},
    )
    assert client.get("/api/admin/airlines").status_code == 200
    again = client.post(
        "/tasks/operator-invite",
        json={"name": "X. Ray", "email": "x@tephra.example"},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert error_of(again) == "operators_exist"


def test_17_no_token_in_any_route_and_no_email_in_any_airline_record(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    templates = [
        str(c.path_format)
        for c in iter_route_contexts(app.routes)
        if isinstance(c.original_route, APIRoute)
    ]
    assert not [t for t in templates if "token" in t.lower()]
    for icao in ("RFB", "RFC"):
        assert "@" not in json.dumps(_entries(site, client, icao))


# --- 19. the shadow stamp survives edit then approve -------------------------------------------


def test_19_a_shadow_draft_keeps_its_stamp_through_edit_and_approve(
    stub_models: None, client: TestClient, site: HostedSite, two: Two
) -> None:
    rfb = site.reg.handle("RFB")
    assert rfb is not None
    runtime = rfb.runtime
    assert runtime is not None

    async def draft() -> None:
        await _drafts(runtime)

    site.run(client, draft)
    as_login(client, site, two.dee)
    advisories = client.get("/a/RFB/api/desk/advisories").json()["advisories"]
    assert advisories
    first = advisories[0]
    assert first["shadow"] is True
    assert "SHADOW - NOT FOR USE" in first["header"]
    edited = call(
        client,
        "POST",
        f"/a/RFB/api/desk/advisories/{first['id']}/edit",
        json={
            "version": first["version"],
            "body": "HOLD PRESENT POSITION. REPORT VAR.",
            "reason": "Crew asks",
        },
    )
    assert edited.status_code == 200, edited.text
    outbound = client.get("/a/RFB/api/outbound").json()["messages"]
    assert outbound
    assert all("SHADOW - NOT FOR USE" in m["text"] for m in outbound), outbound


# --- 20. a rollout: two instances on one store --------------------------------------------------


def test_20_a_retired_instance_s_airlines_write_nothing(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    rfb = site.reg.handle("RFB")
    assert rfb is not None
    assert site.demo is not None
    site.demo.retired = True
    meter = cast(FastAPI, client.app).state.meter
    before = meter.day().writes.get("RFB", 0)
    site.run(client, site.reg.run_pass)
    assert meter.day().writes.get("RFB", 0) == before
    site.demo.retired = False


def test_20_the_meter_persists_by_max_and_never_lowers_a_count(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    meter = cast(FastAPI, client.app).state.meter
    meter.count("RFB", "reads", 50)

    async def persist_twice() -> dict[str, Any] | None:
        await meter.persist(site.root, allowed=True, force=True)
        other = type(meter)(blob_puts_cap=site.settings.hosted_blob_puts_cap)
        other.count("RFB", "reads", 5)
        await other.persist(site.root, allowed=True, force=True)
        return await site.root.get(Collection.HOSTED_METER, meter.day().day.isoformat())

    stored = site.run(client, persist_twice)
    assert stored is not None
    assert stored["reads"]["RFB"] >= 50


# --- 21. invite races ----------------------------------------------------------------------------


def test_21_two_accepts_of_one_link_make_one_member(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    as_login(client, site, two.rfb.login, two.rfb.record)
    link = call(
        client,
        "POST",
        "/a/RFB/api/tenant/people/invites",
        json={"email": "sam@nowhere.example", "role": "viewer"},
    ).json()["link"]
    token = link.split("#", 1)[1]
    cookie = site.cookie(two.sam)

    async def race() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            body = {"token": token, "display_name": "Sam S"}
            jar = {"cookie": f"{AIRLINE_COOKIE}={cookie}"}
            return await asyncio.gather(
                *(ac.post("/api/hosted/invites/accept", json=body, headers=jar) for _ in range(2))
            )

    answered = site.run(client, race)
    assert sorted(a.status_code for a in answered)[0] == 200
    assert sorted(a.status_code for a in answered)[1] in {404, 409}
    people = client.get("/a/RFB/api/tenant/people").json()["members"]
    assert [m["name"] for m in people].count("Sam S") == 1


# --- 22. delete-data waits 7 days -----------------------------------------------------------------


def test_22_data_is_not_deleted_before_seven_days(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    site.run(client, lambda: _suspend(site, "RFB"))
    refused = site.run(
        client,
        lambda: _expect_refusal(site, "RFB"),
    )
    assert refused == "too_soon"


async def _expect_refusal(site: HostedSite, icao: str) -> str:
    from tephra.hosted.models import HostedRefused

    try:
        await tenants.mark_deleting(
            site.root, icao, by="operator:M. Tan#4f1c2a9b", at=wall_clock_now()
        )
    except HostedRefused as refused:
        return refused.code
    return "deleted"


def test_21_removing_an_ops_manager_revokes_their_invites_and_a_demote_race_keeps_one(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    app = cast(FastAPI, client.app)
    _, ole = site.run(
        client, lambda: site.person("RFB", "ops_manager", "ole@rfb.example", "Ole O", by=two.ana)
    )
    ole_login = site.run(client, lambda: accounts.get_login(site.root, ole.login_key))
    assert ole_login is not None
    as_login(client, site, ole_login)
    made = call(
        client,
        "POST",
        "/a/RFB/api/tenant/people/invites",
        json={"email": "pat@rfb.example", "role": "viewer"},
    )
    assert made.status_code == 200, made.text
    as_login(client, site, two.rfb.login, two.rfb.record)
    removed = call(client, "POST", f"/a/RFB/api/tenant/people/{ole.id}/remove")
    assert removed.status_code == 200, removed.text
    assert removed.json()["invites"] == []
    # two ops managers demoting each other at the same moment: one ops manager remains
    _, una = site.run(
        client, lambda: site.person("RFB", "ops_manager", "una@rfb.example", "Una U", by=two.ana)
    )
    una_login = site.run(client, lambda: accounts.get_login(site.root, una.login_key))
    assert una_login is not None
    ana_cookie = site.cookie(two.rfb.login, two.rfb.record)
    una_cookie = site.cookie(una_login)

    async def race() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return await asyncio.gather(
                ac.post(
                    f"/a/RFB/api/tenant/people/{una.id}/role",
                    json={"role": "dispatcher"},
                    headers={"cookie": f"{AIRLINE_COOKIE}={ana_cookie}"},
                ),
                ac.post(
                    f"/a/RFB/api/tenant/people/{two.ana.id}/role",
                    json={"role": "dispatcher"},
                    headers={"cookie": f"{AIRLINE_COOKIE}={una_cookie}"},
                ),
            )

    site.run(client, race)
    record = site.run(client, lambda: tenants.get_tenant(site.root, "RFB"))
    assert record is not None
    assert len(record.ops_managers) == 1


# --- 7 (continued): the root hosted and operator routes stamp wall time ------------------------


def test_7_set_up_accept_and_suspend_over_http_stamp_the_wall_clock(
    client: TestClient, site: HostedSite
) -> None:
    with timeutil.use_clock(timeutil.FixedClock(datetime(2020, 1, 1, tzinfo=UTC))):
        holder = site.run(client, lambda: site.holder("RFB"))
        as_login(client, site, holder.login, holder.record)
        assert client.post("/api/hosted/setup", json={"display_name": "Ana Ops"}).status_code == 200
        link = call(
            client,
            "POST",
            "/a/RFB/api/tenant/people/invites",
            json={"email": "sam@nowhere.example", "role": "viewer"},
        ).json()["link"]
        sam = site.run(
            client,
            lambda: accounts.create_member_login(
                site.root,
                email="sam@nowhere.example",
                password_hash="scrypt$test",
                recovery_sha256="0" * 64,
                at=wall_clock_now(),
            ),
        )
        as_login(client, site, sam)
        accepted = call(
            client,
            "POST",
            "/api/hosted/invites/accept",
            json={"token": link.split("#", 1)[1], "display_name": "Sam S"},
        )
        assert accepted.status_code == 200, accepted.text
        client.cookies.clear()
        minted = client.post(
            "/tasks/operator-invite",
            json={"name": "M. Tan", "email": OPERATOR_EMAIL},
            headers={TASK_HEADER: TASK_TOKEN},
        ).json()
        client.post(
            "/api/admin/invite/accept",
            json={
                "token": minted["link"].split("#", 1)[1],
                "email": OPERATOR_EMAIL,
                "password": PASSWORD,
            },
        )
        expires = datetime.fromisoformat(minted["expires_at"])
        assert abs((expires - wall_clock_now() - timedelta(hours=24)).total_seconds()) < 5
        suspended = call(client, "POST", "/api/admin/tenants/RFB/suspend", json={"reason": "Test"})
        assert suspended.status_code == 200, suspended.text
        entries = _entries(site, client, "RFB")
    by_action = {entry["action"]: datetime.fromisoformat(entry["at"]) for entry in entries}
    for action in (
        AuditAction.HOSTED_SETUP,
        AuditAction.MEMBER_JOINED,
        AuditAction.HOSTED_SUSPENDED,
    ):
        assert abs((by_action[action.value] - wall_clock_now()).total_seconds()) < 5, action


# --- 13 (continued): a password change ------------------------------------------------------------


def test_13_a_recovery_signs_every_other_browser_out_of_the_airline_at_once(
    client: TestClient, site: HostedSite, two: Two
) -> None:
    code = "ABCD-EFGH-JKLM-NPQR"

    async def recoverable() -> AirlineLogin:
        made = await accounts.create_member_login(
            site.root,
            email="rae@rfb.example",
            password_hash=await passwords.hashed(PASSWORD),
            recovery_sha256=passwords.code_sha256(code),
            at=wall_clock_now(),
        )
        _, token = await members.invite(
            site.root,
            "RFB",
            "rae@rfb.example",
            "viewer",
            by=two.ana,
            space=site.reg.space("RFB"),
            at=wall_clock_now(),
        )
        await members.accept(
            site.root,
            token,
            made,
            "Rae R",
            space=site.reg.space("RFB"),
            access=site.reg.access,
            at=wall_clock_now(),
        )
        return made

    rae = site.run(client, recoverable)
    as_login(client, site, rae)
    old = site.cookie(rae)
    assert client.get("/a/RFB/api/desk/me").status_code == 200
    client.cookies.clear()
    recovered = client.post(
        "/api/airline/recover",
        json={"email": "rae@rfb.example", "recovery_code": code, "new_password": PASSWORD + "!"},
    )
    assert recovered.status_code == 200, recovered.text
    assert client.get("/a/RFB/api/desk/me").status_code == 200  # the new cookie works
    client.cookies.clear()
    client.cookies.set(AIRLINE_COOKIE, old)
    assert error_of(client.get("/a/RFB/api/desk/me")) == "no_such_airline"


# --- 20 (continued): two instances on one store ---------------------------------------------------


def test_20_a_second_instance_starts_with_its_cache_off_until_its_first_pass(
    tmp_path: Path, client: TestClient, site: HostedSite, two: Two
) -> None:
    second = HostedSite(tmp_path)
    with TestClient(second.app) as other:
        rfb = second.reg.handle("RFB")
        assert rfb is not None
        assert rfb.space.store._cache_on is False
        assert rfb.runtime is not None  # restored from the same store, without a pass
        site.run(client, site.reg.run_pass)
        assert site.reg.handle("RFB").space.store._cache_on is True  # type: ignore[union-attr]
        assert rfb.space.store._cache_on is False
        second.run(other, second.reg.run_pass)
        assert rfb.space.store._cache_on is True
