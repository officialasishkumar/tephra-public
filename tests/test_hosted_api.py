"""The hosted HTTP API over the real hosted domain and runtimes (SPEC §4): the root hosted
routes, every airline route of /a/<ICAO>/api/tenant, and the airline account changes.

``HostedSite`` is the app with ``hosted`` on: a real demo runtime on fixture feeds (metered as
the demo), the real ``TenantRegistry``, and airline runtimes made by ``create_runtime`` over the
same fixture source. The stub model only; no network. tests/test_admin_api.py and
tests/test_hosted_isolation.py build on it.
"""

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from tephra.agents.llm import get_llm
from tephra.airline import accounts, passwords
from tephra.airline.models import AirlineLogin, AirlineRecord, Stamp
from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.airline.sessions import claims_of, member_claims, sign_claims
from tephra.api import server
from tephra.api.auth import CSRF_HEADER, wall_clock_now
from tephra.api.routes_pages import WEB_DIR
from tephra.config import Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.volcanoes import load_volcanoes
from tephra.hosted import members, tenants
from tephra.hosted.models import Member
from tephra.hosted.registry import TenantRegistry
from tephra.models import AuditAction, RunMode
from tephra.pipeline import Runtime, create_runtime
from tephra.store.base import Collection, Store
from tephra.store.metered import MeteredStore, StoreMeter
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tests.test_hosted_runtime import rfb_aircraft
from tests.test_hosted_tenants import OPERATOR, answers
from tests.test_pipeline import DATA_DIR, POLICY, ROUTES, FixtureSource

T = TypeVar("T")

SECRET = "hosted-api-session-secret-0123456789abcdef"
TASK_TOKEN = "task-token-for-tests-0123456789abcdef"
PIN = "zulu-4711"
PASSWORD = "correct horse battery staple"
GEMINI_KEY = "AIzaRFB-test-key-0123456789abcdefghijklmn"
JSON_HEADERS = {CSRF_HEADER: "1"}
NAMES = {
    "RFB": "Ring of Fire Charter",
    "RFC": "Ring of Fire Cargo",
    "RFD": "Ring of Fire Delta",
    "RFE": "Ring of Fire Express",
}


def site_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "llm": "stub",
        "store": "sqlite",
        "sqlite_path": tmp_path / "state" / "tephra.sqlite3",
        "cache_dir": tmp_path / "cache",
        "desk_pin": PIN,
        "task_token": TASK_TOKEN,
        "session_secret": SECRET,
        "local_scheduler": False,
        "recovery_auto": False,
        "features": "connect,crew,notices,onboard,hosted",
    }
    return Settings(_env_file=None, **(values | overrides))


@dataclass
class Holder:
    record: AirlineRecord
    login: AirlineLogin
    email: str


class HostedSite:
    """The app with hosted on, and the helpers that put airlines and people in place."""

    def __init__(self, tmp_path: Path, **overrides: Any) -> None:
        self.settings = site_settings(tmp_path, **overrides)
        self.settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.source = FixtureSource(rfb_aircraft())
        self.rss = 100
        self.demo: Runtime | None = None
        self.registry: TenantRegistry | None = None
        self.factory: Callable[..., Awaitable[Runtime]] = create_runtime
        self.app = server.create_app(
            self.settings,
            runtime_factory=self.demo_runtime,
            registry_factory=self.make_registry,
        )

    async def demo_runtime(self, settings: Settings, *, meter: StoreMeter) -> Runtime:
        store = MeteredStore(
            SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs"), meter, "demo"
        )
        self.demo = Runtime(
            settings=settings,
            store=store,
            bus=EventBus(),
            source=FixtureSource(),
            llm=get_llm(settings),
            catalogue=load_volcanoes(DATA_DIR),
            airports=load_airports(DATA_DIR, min_runway_m=POLICY.alternates.min_runway_m.value),
            routes=ROUTES,
            policy=POLICY,
            mode=RunMode.LIVE,
            replay_case=None,
            auto_replay=False,
        )
        return self.demo

    def make_registry(
        self, settings: Settings, root: Store, demo: Runtime, meter: StoreMeter, access: Any
    ) -> TenantRegistry:
        async def factory(*args: Any, **kwargs: Any) -> Runtime:
            return await self.factory(*args, **kwargs)

        self.registry = TenantRegistry(
            settings,
            root,
            demo,
            meter,
            access,
            factory=factory,
            source=self.source,
            rss_mb=lambda: self.rss,
        )
        return self.registry

    # --- in the app's own event loop ------------------------------------------------------

    @property
    def root(self) -> Store:
        assert self.demo is not None, "the app has not started"
        return self.demo.store

    @property
    def reg(self) -> TenantRegistry:
        assert self.registry is not None, "the app has not started"
        return self.registry

    def run(self, client: TestClient, call: Callable[[], Awaitable[T]]) -> T:
        portal = client.portal
        assert portal is not None, "use the client as a context manager"
        return cast(T, portal.call(call))

    async def holder(self, icao: str, *, hosting: bool = True, verified: bool = True) -> Holder:
        """An airline account with a real password, submitted and verified (by an operator,
        which approves hosting, unless ``hosting`` is False: the Desk's verify)."""
        email = f"ana@{icao.lower()}.example"
        at = wall_clock_now()
        record, login = await accounts.create_account(
            self.root,
            email=email,
            password_hash=await passwords.hashed(PASSWORD),
            recovery_sha256="0" * 64,
            at=at,
        )
        record = await accounts.submit(
            self.root,
            record.id,
            version=record.version,
            answers=answers(icao, NAMES[icao]),
            flags=[],
            at=at,
        )
        if verified:
            record = await accounts.decide(
                self.root,
                record.id,
                version=record.version,
                actor=OPERATOR if hosting else "desk:Dee",
                verified=True,
                note=None,
                at=at,
                hosting=Stamp(by=OPERATOR, at=at) if hosting else None,
            )
        return Holder(record, login, email)

    async def airline(self, icao: str, state: str = "shadow") -> tuple[Holder, Member]:
        """An airline set up by its holder (Ana Ops, ops manager) and moved to ``state``
        through the domain, with its runtime started by the registry."""
        held = await self.holder(icao)
        at = wall_clock_now()
        _, member = await tenants.set_up(
            self.root,
            held.record,
            held.login,
            "Ana Ops",
            space=self.reg.space(icao),
            settings=self.settings,
            base_policy=self.reg.demo.policy,
            airports=self.reg.demo.airports,
            at=at,
        )
        await self.reg.reload(icao)
        by = tenants.member_by(member)
        space = self.reg.space(icao)
        if state in {"shadow", "live", "suspended"}:
            await tenants.start(
                self.root,
                icao,
                region="java_bali",
                by=by,
                max_slots=self.settings.hosted_max_tenants,
                space=space,
                at=at,
            )
            await self.reg.start(icao)
        if state == "live":
            await tenants.go_live(self.root, icao, by=by, space=space, at=at)
            await self.reg.reconfigure(icao)
        if state == "suspended":
            await tenants.suspend(
                self.root, icao, by=OPERATOR, reason="test suspension", space=space, at=at
            )
            await self.reg.stop(icao, reason="test")
        await self.reg.reload(icao)
        return held, member

    async def person(
        self, icao: str, role: str, email: str, name: str, *, by: Member
    ) -> tuple[AirlineLogin, Member]:
        """A member-only login invited by ``by`` and joined (a real invite and accept)."""
        at = wall_clock_now()
        space = self.reg.space(icao)
        _, token = await members.invite(self.root, icao, email, role, by=by, space=space, at=at)  # type: ignore[arg-type]
        login = await accounts.create_member_login(
            self.root,
            email=email,
            password_hash=await passwords.hashed(PASSWORD),
            recovery_sha256="0" * 64,
            at=at,
        )
        member = await members.accept(
            self.root, token, login, name, space=space, access=self.reg.access, at=at
        )
        await self.reg.reload(icao)
        return login, member

    def cookie(self, login: AirlineLogin, record: AirlineRecord | None = None) -> str:
        claims = member_claims(login) if record is None else claims_of(record, login)
        token, _ = sign_claims(claims, self.settings, at=wall_clock_now())
        return token


def as_login(
    client: TestClient, site: HostedSite, login: AirlineLogin, record: AirlineRecord | None = None
) -> TestClient:
    client.cookies.clear()
    client.cookies.set(AIRLINE_COOKIE, site.cookie(login, record))
    return client


def error_of(response: httpx.Response) -> str:
    return str(response.json()["error"])


def entries_of(site: HostedSite, client: TestClient, icao: str) -> list[dict[str, Any]]:
    space = site.reg.space(icao)

    async def read() -> list[dict[str, Any]]:
        with space.bound():
            return await space.store.list_docs(
                Collection.AUDIT, limit=500, order_by="seq", descending=False
            )

    return site.run(client, read)


@pytest.fixture(autouse=True)
def _no_startup_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    """The demo's startup tick would run the whole pipeline on fixture feeds for nothing here."""

    async def skip(runtime: Runtime) -> None:
        return None

    monkeypatch.setattr(server, "_startup_tick", skip)


@pytest.fixture
def site(tmp_path: Path) -> HostedSite:
    return HostedSite(tmp_path)


@pytest.fixture
def client(site: HostedSite) -> Iterator[TestClient]:
    with TestClient(site.app, follow_redirects=False) as test_client:
        yield test_client


# --- set up and Go live, end to end -----------------------------------------------------


def test_from_verified_to_shadow_to_live_and_back(client: TestClient, site: HostedSite) -> None:
    holder = site.run(client, lambda: site.holder("RFB"))
    as_login(client, site, holder.login, holder.record)
    me = client.get("/api/hosted/me").json()
    assert me == {
        "memberships": [],
        "can_set_up": {"icao": "RFB", "name": NAMES["RFB"]},
        "waiting": None,
        "max_airlines": site.settings.hosted_max_tenants,
    }

    header = client.post("/api/hosted/setup", json={"display_name": "Ana Ops"})
    assert header.status_code == 200, header.text
    assert header.json()["state"] == "setup"
    assert header.json()["you"]["role"] == "ops_manager"
    assert error_of(client.post("/api/hosted/setup", json={"display_name": "Ana Ops"})) in {
        "already_set_up",
        "icao_taken",
    }

    golive = client.get("/a/RFB/api/tenant/golive").json()
    assert golive["can_start"] is False
    assert golive["blocked"] == "checklist"
    assert (
        error_of(client.post("/a/RFB/api/tenant/start", json={"region": "java_bali"}))
        == "checklist_open"
    )

    # feeds: a push key, and a push while in setup (checked and counted, not taken in)
    made = client.post("/a/RFB/api/tenant/keys", json={"name": "Ops system"})
    assert made.status_code == 200, made.text
    key = made.json()["key"]
    listed = client.get("/a/RFB/api/tenant/keys")
    assert key
    assert key not in listed.text
    assert [k["key"] for k in listed.json()["keys"]] == [None]
    push = httpx_push(client, "RFB", key, positions=[position()])
    assert push.status_code == 202, push.text
    assert push.json()["taken_in"] is False
    assert push.json()["result"]["positions"]["accepted"] == 1
    feeds = client.get("/a/RFB/api/tenant/feeds").json()
    assert feeds["taken_in"] is False
    assert feeds["cards"][0]["records_last_hour"] == 1
    assert feeds["keys"][0]["sections_seen"] == ["positions"]

    # assistant: the model and a key (a bad key is refused without a word of it)
    tab = client.put(
        "/a/RFB/api/tenant/assistant",
        json={
            "model": "gemini-3.8-flash",
            "model_lite": "gemini-3.5-flash-lite",
            "reserve_share": 0.2,
            "daily_limits": {},
        },
    )
    assert tab.status_code == 200, tab.text
    bad = client.put("/a/RFB/api/tenant/assistant/key", json={"key": "not a key at all!"})
    assert (bad.status_code, error_of(bad)) == (422, "key_format")
    assert "not a key" not in bad.text
    keyed = client.put("/a/RFB/api/tenant/assistant/key", json={"key": GEMINI_KEY})
    assert keyed.status_code == 200, keyed.text
    assert keyed.json()["key"] == {
        "set": True,
        "last4": GEMINI_KEY[-4:],
        "set_by": keyed.json()["key"]["set_by"],
        "readable": True,
    }
    assert GEMINI_KEY[:12] not in keyed.text

    # policy confirmed, and a dispatcher who joined by invite
    assert client.post("/a/RFB/api/tenant/policy/confirm", json={"version": 1}).status_code == 200
    invited = client.post(
        "/a/RFB/api/tenant/people/invites", json={"email": "dee@rfb.example", "role": "dispatcher"}
    )
    assert invited.status_code == 200, invited.text
    link = invited.json()["link"]
    assert link.startswith("http://testserver/join#")
    token = link.split("#", 1)[1]
    # opened while signed in as the record holder: the page is told who that is, masked, and
    # that the invite is for another email
    mine = client.post("/api/hosted/invites/lookup", json={"token": token}).json()["you"]
    assert mine["for_you"] is False
    assert mine["email_hint"].endswith("@rfb.example")
    assert "•••" in mine["email_hint"]
    assert mine["name"] == "Ana Ops"
    client.cookies.clear()
    looked = client.post("/api/hosted/invites/lookup", json={"token": token})
    assert looked.status_code == 200, looked.text
    assert looked.json()["email_hint"].startswith("d")
    assert looked.json()["you"] is None
    assert "dee@" not in looked.text
    joined = client.post(
        "/api/hosted/invites/join",
        json={
            "token": token,
            "email": "dee@rfb.example",
            "password": PASSWORD,
            "display_name": "Dee Dispatch",
            "acknowledge": True,
        },
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["recovery_code"]
    assert client.get("/a/RFB/api/desk/me").json()["role"] == "dispatcher"
    assert (
        error_of(client.post("/api/hosted/invites/lookup", json={"token": token})) == "invite_gone"
    )

    as_login(client, site, holder.login, holder.record)
    golive = client.get("/a/RFB/api/tenant/golive").json()
    assert [item["done"] for item in golive["items"]] == [True, True, True, True], golive
    assert golive["can_start"] is True
    started = client.post(
        "/a/RFB/api/tenant/start",
        json={"region": golive["region"]["key"] if golive["region"] else "java_bali"},
    )
    assert started.status_code == 200, started.text
    assert started.json()["state"] == "shadow"
    assert started.json()["runtime"]["running"] is True
    assert client.get("/a/RFB/api/state").status_code == 200

    wrong = client.post("/a/RFB/api/tenant/live", json={"confirm_icao": "RFX", "attest": True})
    assert (wrong.status_code, error_of(wrong)) == (422, "confirm_icao")
    live = client.post("/a/RFB/api/tenant/live", json={"confirm_icao": "RFB", "attest": True})
    assert live.status_code == 200, live.text
    assert live.json()["state"] == "live"
    assert live.json()["live"]["by"] == "Ana Ops"
    back = client.post("/a/RFB/api/tenant/shadow", json={"reason": "Back for a drill"})
    assert back.json()["state"] == "shadow"
    stopped = client.post("/a/RFB/api/tenant/stop", json={"reason": "End of the trial"})
    assert stopped.json()["state"] == "setup"
    assert stopped.json()["runtime"]["running"] is False
    assert client.get("/a/RFB/api/tenant/golive").json()["slots"]["used"] == 0

    actions = [entry["action"] for entry in entries_of(site, client, "RFB")]
    for action in (
        AuditAction.HOSTED_SETUP,
        AuditAction.CONNECTION_CREATED,
        AuditAction.ASSISTANT_CHANGED,
        AuditAction.MODEL_KEY_SET,
        AuditAction.POLICY_CONFIRMED,
        AuditAction.MEMBER_INVITED,
        AuditAction.MEMBER_JOINED,
        AuditAction.HOSTED_SHADOW,
        AuditAction.HOSTED_LIVE,
        AuditAction.HOSTED_STOPPED,
    ):
        assert action.value in actions, action
    assert "@" not in json.dumps(entries_of(site, client, "RFB"))


def position(**changes: Any) -> dict[str, Any]:
    return {
        "callsign": "RFB417",
        "hex": "8a0b17",
        "lat": -8.15,
        "lon": 113.7,
        "alt_baro_ft": 12000,
        "gs_kt": 420,
        "track_deg": 270,
        "observed_at": wall_clock_now().isoformat().replace("+00:00", "Z"),
        **changes,
    }


def httpx_push(client: TestClient, icao: str, key: str | None, **sections: Any) -> httpx.Response:
    headers = {} if key is None else {"Authorization": f"Bearer {key}"}
    body = {"format": "tephra.airline/1", **sections}
    return client.post(f"/a/{icao}/api/push/positions", json=body, headers=headers)


# --- the airline routes, one by one -----------------------------------------------------


@pytest.fixture
def rfb(client: TestClient, site: HostedSite) -> tuple[Holder, Member]:
    """RFB in SHADOW with its runtime, the client signed in as Ana Ops (its ops manager)."""
    held, member = site.run(client, lambda: site.airline("RFB", "shadow"))
    as_login(client, site, held.login, held.record)
    return held, member


def new_key(client: TestClient, icao: str = "RFB") -> tuple[str, str]:
    made = client.post(f"/a/{icao}/api/tenant/keys", json={"name": "Ops system"})
    assert made.status_code == 200, made.text
    return made.json()["id"], made.json()["key"]


def test_the_header_names_the_reader_and_holds_the_chain_head(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    header = client.get("/a/RFB/api/tenant/header").json()
    assert (header["icao"], header["name"], header["state"]) == ("RFB", NAMES["RFB"], "shadow")
    assert header["you"] == {"name": "Ana Ops", "role": "ops_manager", "member_id": rfb[1].id}
    assert header["memberships"] == [
        {"icao": "RFB", "name": NAMES["RFB"], "role": "ops_manager", "state": "shadow"}
    ]
    assert header["runtime"]["running"] is True
    assert header["chain"]["entries"] >= 2
    assert header["policy"]["label"] == "ILLUSTRATIVE, not an airline SRA"


def test_a_running_push_is_taken_under_the_airline_s_limits(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    _, key = new_key(client)
    taken = httpx_push(client, "RFB", key, positions=[position()])
    assert taken.status_code == 200, taken.text
    assert taken.json()["accepted"] == 1
    again = httpx_push(client, "RFB", key, positions=[position()])
    assert (again.status_code, error_of(again)) == (429, "too_many_pushes")
    assert int(again.headers["retry-after"]) >= 1
    card = client.get("/a/RFB/api/tenant/feeds").json()["cards"][0]
    assert card["records_last_hour"] == 1


def test_rotating_a_key_stops_the_old_one_at_once_and_revoke_stops_the_new(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    key_id, old = new_key(client)
    rotated = client.post(f"/a/RFB/api/tenant/keys/{key_id}/rotate", json={})
    assert rotated.status_code == 200, rotated.text
    new = rotated.json()["key"]
    assert new
    assert new != old
    assert error_of(httpx_push(client, "RFB", old, positions=[position()])) == "bad_key"
    assert httpx_push(client, "RFB", new, positions=[position()]).status_code == 200
    new_id = rotated.json()["id"]
    assert client.post(f"/a/RFB/api/tenant/keys/{new_id}/revoke", json={}).status_code == 200
    assert error_of(httpx_push(client, "RFB", new, positions=[position()])) == "bad_key"
    assert client.post("/a/RFB/api/tenant/keys/CN-0000000000/rotate", json={}).status_code == 404
    assert client.post("/a/RFB/api/tenant/keys/nonsense/revoke", json={}).status_code == 404


def test_a_dry_run_takes_nothing_in_and_counts_as_a_check(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    body = {"format": "tephra.airline/1", "positions": [position(), {"hex": "zz"}]}
    checked = client.post("/a/RFB/api/tenant/feeds/dry-run", json=body)
    assert checked.status_code == 200, checked.text
    assert checked.json()["positions"]["accepted"] == 1
    assert len(checked.json()["rejected"]) == 1
    card = client.get("/a/RFB/api/tenant/feeds").json()["cards"][0]
    assert card["refused_last_hour"] == 1
    assert card["last_received_at"] is None  # a check of a file is not a feed received
    assert error_of(client.post("/a/RFB/api/tenant/feeds/dry-run", json=[1])) == "not_a_push"


def test_an_upload_is_never_retimed_for_an_airline(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    body = {"format": "tephra.positions/1", "positions": [position()]}
    refused = client.post("/a/RFB/api/desk/upload", json={**body, "retime": True})
    assert (refused.status_code, error_of(refused)) == (422, "retime_not_on_hosted")
    assert client.post("/a/RFB/api/desk/upload", json={**body, "retime": False}).status_code == 200
    assert client.post("/a/RFB/api/desk/upload", json=body).json()["accepted"] == 1


def test_policy_versions_confirmation_and_the_sra_label(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    tab = client.get("/a/RFB/api/tenant/policy").json()
    assert tab["current"]["version"] == 1
    assert tab["label"] == "ILLUSTRATIVE, not an airline SRA"
    change = {
        "name": "exposure.vertical_margin_ft",
        "value": 4000,
        "reason": "Company SOP 4.2 asks for more",
    }
    stale = client.post("/a/RFB/api/tenant/policy", json={"base_version": 9, "changes": [change]})
    assert error_of(stale) == "version_conflict"
    saved = client.post("/a/RFB/api/tenant/policy", json={"base_version": 1, "changes": [change]})
    assert saved.status_code == 200, saved.text
    assert saved.json()["current"]["version"] == 2
    assert site.reg.handle("RFB").runtime.policy.version == "RFB-2"  # type: ignore[union-attr]
    assert client.post("/a/RFB/api/tenant/policy/confirm", json={"version": 2}).status_code == 200
    sra = {"version": 2, "accepted_by": "Capt. Ana Ops", "accepted_on": "2026-10-01"}
    accepted = client.post("/a/RFB/api/tenant/policy/sra", json=sra)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["label"].startswith(f"Accepted under {NAMES['RFB']}'s SRA")
    assert "TEPHRA does not check it" in accepted.json()["label"]
    withdrawn = client.post("/a/RFB/api/tenant/policy/sra/withdraw", json={"reason": "Re-review"})
    assert withdrawn.json()["label"] == "ILLUSTRATIVE, not an airline SRA"


def test_the_assistant_key_is_write_only_and_can_be_removed(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    keyed = client.put("/a/RFB/api/tenant/assistant/key", json={"key": GEMINI_KEY})
    assert keyed.json()["key"]["last4"] == GEMINI_KEY[-4:]
    tab = client.get("/a/RFB/api/tenant/assistant")
    assert GEMINI_KEY[:8] not in tab.text
    assert tab.json()["budget"] is not None
    removed = client.delete("/a/RFB/api/tenant/assistant/key", headers=JSON_HEADERS)
    assert removed.status_code == 200, removed.text
    assert removed.json()["key"]["set"] is False
    assert removed.json()["state"] == "unavailable"
    runtime = site.reg.handle("RFB").runtime  # type: ignore[union-attr]
    assert runtime is not None
    assert runtime.settings.gemini_api_key is None


def test_people_roles_removal_and_the_last_ops_manager(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    _, dee = site.run(
        client, lambda: site.person("RFB", "dispatcher", "dee@rfb.example", "Dee D", by=rfb[1])
    )
    people = client.get("/a/RFB/api/tenant/people").json()
    assert {m["name"] for m in people["members"]} == {"Ana Ops", "Dee D"}
    assert {m["email"] for m in people["members"]} == {"ana@rfb.example", "dee@rfb.example"}
    role = client.post(f"/a/RFB/api/tenant/people/{dee.id}/role", json={"role": "viewer"})
    assert role.status_code == 200, role.text
    assert {m["name"]: m["role"] for m in role.json()["members"]}["Dee D"] == "viewer"
    alone = client.post("/a/RFB/api/tenant/people/me/leave", json={})
    assert (alone.status_code, error_of(alone)) == (409, "last_ops_manager")
    demote = client.post(f"/a/RFB/api/tenant/people/{rfb[1].id}/role", json={"role": "viewer"})
    assert error_of(demote) == "last_ops_manager"
    removed = client.post(f"/a/RFB/api/tenant/people/{dee.id}/remove", json={})
    assert [m["name"] for m in removed.json()["members"]] == ["Ana Ops"]
    assert client.post("/a/RFB/api/tenant/people/MB-nothing/remove", json={}).status_code == 404


def test_an_invite_link_is_shown_once_and_can_be_revoked(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    made = client.post(
        "/a/RFB/api/tenant/people/invites", json={"email": "VIC@rfb.example", "role": "viewer"}
    )
    assert made.status_code == 200, made.text
    invite = made.json()["invite"]
    assert invite["email"] == "vic@rfb.example"
    token = made.json()["link"].split("#", 1)[1]
    people = client.get("/a/RFB/api/tenant/people")
    assert token not in people.text
    assert [i["id"] for i in people.json()["invites"]] == [invite["id"]]
    revoked = client.post(f"/a/RFB/api/tenant/people/invites/{invite['id']}/revoke", json={})
    assert revoked.json()["invites"] == []
    assert error_of(client.post("/api/hosted/invites/lookup", json={"token": token})) == (
        "invite_gone"
    )


def test_the_record_pages_checks_and_exports_once_a_day(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    tab = client.get("/a/RFB/api/tenant/record").json()
    assert tab["entries"][0]["seq"] > tab["entries"][-1]["seq"]
    assert tab["head"]["intact"] is True
    assert (tab["can_check"], tab["can_export"]) == (True, True)
    checked = client.post("/a/RFB/api/tenant/record/check", json={})
    assert checked.status_code == 200, checked.text
    assert checked.json()["entries"][0]["action"] == AuditAction.CHAIN_CHECKED.value
    assert checked.json()["can_check"] is False
    assert client.post("/a/RFB/api/tenant/record/check", json={}).status_code == 429
    exported = client.get("/a/RFB/api/tenant/record/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/x-ndjson")
    disposition = exported.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="RFB-record-')
    lines = [json.loads(line) for line in exported.text.splitlines()]
    assert [entry["seq"] for entry in lines] == list(range(1, len(lines) + 1))
    assert client.get("/a/RFB/api/tenant/record/export").status_code == 429
    older = client.get(f"/a/RFB/api/tenant/record?before_seq={lines[-1]['seq']}").json()
    assert all(entry["seq"] < lines[-1]["seq"] for entry in older["entries"])


def test_the_uploader_is_a_member_s_download_with_nothing_of_the_airline_in_it(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    """FOLLOWUP (owner, 17 Oct: the setup kit is dropped, push.py stays): the Feeds page offers
    kit/push.py as "Download uploader" to the airline's people only, as a file to save."""
    tool = (WEB_DIR / "kit" / "push.py").read_bytes()
    _, key = new_key(client)
    got = client.get("/a/RFB/api/tenant/feeds/uploader")
    assert got.status_code == 200, got.text
    assert got.headers["content-disposition"] == 'attachment; filename="push.py"'
    assert got.headers["content-type"].startswith("text/x-python")
    assert got.headers["cache-control"] == "private, no-store"
    assert got.content == tool  # the same file for everyone: nothing written into it
    text = got.text
    for secret in (key, GEMINI_KEY, SECRET, TASK_TOKEN, PIN, "AIza"):
        assert secret not in text
    assert not re.search(r"tph_[A-Za-z0-9_]{12,}", text)
    # a viewer may download it too; someone who is not one of RFB's people may not
    viewer, _ = site.run(
        client, lambda: site.person("RFB", "viewer", "vic@rfb.example", "Vic V", by=rfb[1])
    )
    as_login(client, site, viewer)
    assert client.get("/a/RFB/api/tenant/feeds/uploader").content == tool
    other, _ = site.run(client, lambda: site.airline("RFC", "setup"))
    as_login(client, site, other.login, other.record)
    stranger = client.get("/a/RFB/api/tenant/feeds/uploader")
    assert (stranger.status_code, error_of(stranger)) == (404, "no_such_airline")
    assert "push.py" not in stranger.headers.get("content-disposition", "")
    assert client.get("/a/RFC/api/tenant/feeds/uploader").content == tool
    client.cookies.clear()
    assert client.get("/a/RFB/api/tenant/feeds/uploader").status_code == 401
    # never a public static file while hosting is on (GET or HEAD), and not under the root API
    for method in ("GET", "HEAD"):
        public = client.request(method, "/static/kit/push.py")
        assert public.status_code == 404, method
        assert public.content in (
            b"",
            b'{"error":"not_found","detail":"No such file","problems":[],"current":null}',
        )
    assert client.get("/static/kit/__pycache__/x.pyc").status_code == 404
    assert client.get("/api/tenant/feeds/uploader").status_code == 404
    # a path the /static/kit/ route does not match, which the static files normalise (merge
    # verify, 17 Oct: these were served signed out)
    for raw in ("/static//kit/push.py", "/static///kit//push.py"):
        assert client.get(raw).status_code == 404, raw


@pytest.mark.parametrize(
    "raw",
    [
        "/static//kit/push.py",
        "/static///kit//push.py",
        "/static/./kit/push.py",
        "/static/x/../kit/push.py",
        "/static/KIT/push.py",
        "/static/Kit/./push.py",
    ],
)
def test_no_spelling_of_the_kit_path_gets_past_the_page_files(raw: str) -> None:
    """The static files resolve ``//``, ``.`` and ``..`` themselves (and a macOS disk ignores
    case), so the hosted guard reads the path they resolve, not the URL."""
    scope = {"type": "http", "method": "GET", "path": raw, "root_path": "/static", "headers": []}
    hidden = server.PageFiles(directory=WEB_DIR, check_dir=False, hidden=frozenset({"kit"}))
    with pytest.raises(StarletteHTTPException) as refused:
        asyncio.run(hidden.get_response(hidden.get_path(scope), scope))
    assert refused.value.status_code == 404
    # the same files with hosting off, and every other page file, are served as before
    shown = server.PageFiles(directory=WEB_DIR, check_dir=False, hidden=frozenset())
    plain = {**scope, "path": "/static/kit/push.py"}
    assert asyncio.run(shown.get_response(shown.get_path(plain), plain)).status_code == 200
    page = {**scope, "path": "/static/wall/info.js"}
    assert asyncio.run(hidden.get_response(hidden.get_path(page), page)).status_code == 200


def test_a_check_over_the_airline_s_allowance_is_refused(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    meter = cast(FastAPI, client.app).state.meter
    meter.count("RFB", "reads", 7_999)
    refused = client.post("/a/RFB/api/tenant/record/check", json={})
    assert (refused.status_code, error_of(refused)) == (503, "airline_paused")
    assert client.get("/a/RFB/api/tenant/record/export").status_code == 503


# --- the airline accounts with hosting --------------------------------------------------


def test_a_hosted_airline_s_account_cannot_be_deleted(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    refused = client.post("/api/airline/delete", json={"password": PASSWORD})
    assert (refused.status_code, error_of(refused)) == (409, "hosted_airline")
    wrong = client.post("/api/airline/delete", json={"password": "not the password at all"})
    assert error_of(wrong) == "bad_credentials"


def test_a_member_only_login_signs_in_and_may_delete_itself(
    client: TestClient, site: HostedSite, rfb: tuple[Holder, Member]
) -> None:
    site.run(
        client, lambda: site.person("RFB", "dispatcher", "dee@rfb.example", "Dee D", by=rfb[1])
    )
    client.cookies.clear()
    signed = client.post(
        "/api/airline/sign-in", json={"email": "dee@rfb.example", "password": PASSWORD}
    )
    assert signed.status_code == 200, signed.text
    assert signed.json() == {
        "accounts": True,
        "signed_in": True,
        "icao": None,
        "name": None,
        "status": None,
    }
    assert client.get("/api/airline/me").json()["error"] == "no_airline_record"
    assert [m["icao"] for m in client.get("/api/hosted/me").json()["memberships"]] == ["RFB"]
    people = client.get("/a/RFB/api/tenant/people").json()
    assert {m["name"]: m["last_sign_in_at"] is not None for m in people["members"]}["Dee D"]
    assert {m["email"] for m in people["members"]} == {None}  # emails for ops managers only
    gone = client.post("/api/airline/delete", json={"password": PASSWORD})
    assert gone.status_code == 204, gone.text
    assert client.get("/a/RFB/api/desk/me").status_code == 401


def test_signing_out_signs_out_every_device(client: TestClient, site: HostedSite) -> None:
    held, _ = site.run(client, lambda: site.airline("RFB", "setup"))
    copy = site.cookie(held.login, held.record)
    as_login(client, site, held.login, held.record)
    assert client.get("/a/RFB/api/tenant/header").status_code == 200
    assert client.post("/api/airline/sign-out", json={}).status_code == 204
    client.cookies.set(AIRLINE_COOKIE, copy)
    assert error_of(client.get("/a/RFB/api/tenant/header")) == "no_such_airline"


def test_a_desk_verified_airline_waits_for_an_operator(
    client: TestClient, site: HostedSite
) -> None:
    held = site.run(client, lambda: site.holder("RFB", hosting=False))
    as_login(client, site, held.login, held.record)
    me = client.get("/api/hosted/me").json()
    assert (me["can_set_up"], me["waiting"]) == (None, "hosting_not_approved")
    refused = client.post("/api/hosted/setup", json={"display_name": "Ana Ops"})
    assert (refused.status_code, error_of(refused)) == (409, "hosting_not_approved")


def test_the_airline_routes_exist_only_under_an_airline(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    for path in ("/api/tenant/header", "/api/tenant/record", "/api/tenant/people"):
        answered = client.get(path)
        assert (answered.status_code, error_of(answered)) == (404, "not_found"), path


def test_an_airline_s_dry_run_and_push_take_a_push_sized_body(
    client: TestClient, rfb: tuple[Holder, Member]
) -> None:
    padding = "x" * (64 * 1024)  # four times the site's usual body cap
    body = {"format": "tephra.positions/1", "positions": [position()], "note": padding}
    checked = client.post("/a/RFB/api/tenant/feeds/dry-run", json=body)
    assert checked.status_code != 413, checked.text
    huge = {"format": "tephra.positions/1", "positions": [position()], "note": "x" * 600_000}
    assert client.post("/a/RFB/api/tenant/feeds/dry-run", json=huge).status_code == 413
    _, key = new_key(client)
    assert httpx_push(client, "RFB", key, positions=[position()], note=padding).status_code != 413
