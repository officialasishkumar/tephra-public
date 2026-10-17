"""The operators' console API and the operator tasks (SPEC §4.2, D9, D24, D27, S10, S11):
the bootstrap link that works only while no operator exists, invites, sign-in throttles,
verify with hosting, approve hosting, decline, suspend, resume, delete after 7 days, the
ops-manager invite, the contact, and disabling operators."""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from tephra.airline import accounts
from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.api import routes_admin
from tephra.api.auth import COOKIE_NAME as DESK_COOKIE
from tephra.api.auth import TASK_HEADER, sign_session, wall_clock_now
from tephra.hosted import members, tenants
from tephra.hosted.operators import COOKIE_NAME as OPERATOR_COOKIE
from tests.test_hosted_api import (
    NAMES,
    PASSWORD,
    TASK_TOKEN,
    HostedSite,
    as_login,
    error_of,
    httpx_push,
    position,
)

OPERATOR_EMAIL = "m.tan@tephra.example"


@pytest.fixture
def site(tmp_path: Path) -> HostedSite:
    return HostedSite(tmp_path)


@pytest.fixture
def client(site: HostedSite) -> Iterator[TestClient]:
    with TestClient(site.app, follow_redirects=False) as test_client:
        yield test_client


def bootstrap(client: TestClient, email: str = OPERATOR_EMAIL, name: str = "M. Tan") -> str:
    """The first operator's link from the task, accepted: the client holds its cookie."""
    minted = client.post(
        "/tasks/operator-invite",
        json={"name": name, "email": email},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert minted.status_code == 200, minted.text
    link = minted.json()["link"]
    assert link.startswith("http://testserver/admin/join#")
    token = link.split("#", 1)[1]
    accepted = client.post(
        "/api/admin/invite/accept", json={"token": token, "email": email, "password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    assert OPERATOR_COOKIE in client.cookies
    return str(accepted.json()["k"])


@pytest.fixture
def operator(client: TestClient) -> str:
    return bootstrap(client)


def row_of(client: TestClient, icao: str) -> dict[str, Any]:
    rows = client.get("/api/admin/airlines").json()["rows"]
    return next(row for row in rows if row["icao"] == icao)


def post(client: TestClient, path: str, body: dict[str, Any] | None = None) -> httpx.Response:
    return client.post(path, json=body if body is not None else {})


# --- the first operator and signing in --------------------------------------------------


def test_the_bootstrap_link_needs_the_task_token_and_works_once(
    client: TestClient, site: HostedSite
) -> None:
    body = {"name": "M. Tan", "email": OPERATOR_EMAIL}
    assert client.post("/tasks/operator-invite", json=body).status_code == 403
    wrong = {TASK_HEADER: "not-the-token"}
    assert client.post("/tasks/operator-invite", json=body, headers=wrong).status_code == 403
    bootstrap(client)
    again = client.post("/tasks/operator-invite", json=body, headers={TASK_HEADER: TASK_TOKEN})
    assert (again.status_code, error_of(again)) == (409, "operators_exist")
    me = client.get("/api/admin/me").json()
    assert (me["name"], me["email"], me["you"]) == ("M. Tan", OPERATOR_EMAIL, True)


def test_an_operator_invite_is_bound_to_its_email(client: TestClient) -> None:
    minted = client.post(
        "/tasks/operator-invite",
        json={"name": "M. Tan", "email": OPERATOR_EMAIL},
        headers={TASK_HEADER: TASK_TOKEN},
    ).json()
    token = minted["link"].split("#", 1)[1]
    looked = post(client, "/api/admin/invite/lookup", {"token": token})
    assert looked.status_code == 200
    assert OPERATOR_EMAIL not in looked.text
    wrong = post(
        client,
        "/api/admin/invite/accept",
        {"token": token, "email": "other@tephra.example", "password": PASSWORD},
    )
    assert (wrong.status_code, error_of(wrong)) == (403, "wrong_email")
    gone = post(client, "/api/admin/invite/lookup", {"token": "x" * 43})
    assert error_of(gone) == "invite_gone"


def test_sign_in_says_the_tries_left_and_then_waits(client: TestClient, operator: str) -> None:
    client.cookies.clear()
    wrong = {"email": OPERATOR_EMAIL, "password": "not the password"}
    first = post(client, "/api/admin/sign-in", wrong)
    assert (first.status_code, error_of(first)) == (401, "bad_credentials")
    assert first.headers["x-tephra-tries-left"] == "4"
    assert "not the password" not in first.text
    for _ in range(4):
        post(client, "/api/admin/sign-in", wrong)
    blocked = post(client, "/api/admin/sign-in", {"email": OPERATOR_EMAIL, "password": PASSWORD})
    assert (blocked.status_code, error_of(blocked)) == (429, "too_many_attempts")
    assert int(blocked.headers["retry-after"]) > 0


def test_sign_in_and_out_everywhere(client: TestClient, operator: str) -> None:
    client.cookies.clear()
    signed = post(client, "/api/admin/sign-in", {"email": OPERATOR_EMAIL, "password": PASSWORD})
    assert signed.status_code == 200, signed.text
    held = client.cookies[OPERATOR_COOKIE]
    assert client.get("/api/admin/me").status_code == 200
    assert post(client, "/api/admin/sign-out").status_code == 204
    client.cookies.set(OPERATOR_COOKIE, held)
    assert client.get("/api/admin/me").status_code == 401


def test_every_console_route_refuses_anyone_but_an_operator(
    client: TestClient, site: HostedSite
) -> None:
    paths = [
        ("GET", "/api/admin/airlines"),
        ("GET", "/api/admin/operators"),
        ("GET", "/api/admin/me"),
        ("POST", "/api/admin/airlines/AL-0123456789ab/verify"),
        ("POST", "/api/admin/tenants/RFB/suspend"),
        ("POST", "/api/admin/operators/invites"),
    ]
    for method, path in paths:
        assert client.request(method, path, json={}).status_code == 401, path
    holder = site.run(client, lambda: site.holder("RFB"))
    as_login(client, site, holder.login, holder.record)
    for method, path in paths:
        refused = client.request(method, path, json={})
        assert refused.status_code in {401, 403}, path
    client.cookies.clear()
    token, _ = sign_session("Dee", site.settings, at=wall_clock_now())
    client.cookies.set(DESK_COOKIE, token)
    assert error_of(client.get("/api/admin/airlines")) == "operator_only"
    assert client.get("/api/desk/me").status_code == 200  # the Desk itself still works


def test_an_operator_cookie_is_not_a_desk_session(client: TestClient, operator: str) -> None:
    assert client.get("/api/desk/me").status_code == 401
    assert client.get("/api/desk/advisories").status_code == 401


# --- airlines ---------------------------------------------------------------------------


def test_verify_approves_hosting_and_decline_says_why(
    client: TestClient, site: HostedSite, operator: str
) -> None:
    pending = site.run(client, lambda: site.holder("RFB", verified=False))
    other = site.run(client, lambda: site.holder("RFC", verified=False))
    listed = client.get("/api/admin/airlines").json()
    assert (listed["to_verify"], listed["to_approve"]) == (2, 0)
    assert listed["slots"] == {"used": 0, "max": 3}
    assert listed["hosting"] == "always-on"
    assert "by_namespace" in listed["meter"]
    row = row_of(client, "RFB")
    assert (row["status"], row["status_label"]) == ("pending", "Pending")
    stale = post(client, f"/api/admin/airlines/{pending.record.id}/verify", {"version": 99})
    assert error_of(stale) == "version_conflict"
    verified = post(
        client, f"/api/admin/airlines/{pending.record.id}/verify", {"version": row["version"]}
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "verified"
    assert verified.json()["history"][-1]["actor"].startswith("operator:M. Tan#")
    assert row_of(client, "RFB")["hosting"] == "operator"
    declined = post(
        client,
        f"/api/admin/airlines/{other.record.id}/decline",
        {"version": row_of(client, "RFC")["version"], "reason": "Not an airline we can find"},
    )
    assert declined.json()["status"] == "declined"
    as_login(client, site, pending.login, pending.record)
    me = client.get("/api/hosted/me").json()
    assert me["can_set_up"] == {"icao": "RFB", "name": NAMES["RFB"]}
    assert client.post("/api/admin/airlines/AL-zz/verify", json={"version": 1}).status_code in {
        401,
        403,
        404,
    }


def test_a_desk_verified_airline_needs_an_operator_s_approval(
    client: TestClient, site: HostedSite, operator: str
) -> None:
    holder = site.run(client, lambda: site.holder("RFB", hosting=False))
    row = row_of(client, "RFB")
    assert (row["status_label"], row["hosting"]) == ("Verified (Desk)", "desk")
    approved = post(
        client,
        f"/api/admin/airlines/{holder.record.id}/approve-hosting",
        {"version": row["version"]},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["hosting"] == "operator"


def test_an_airline_staff_verified_while_hosting_was_off_waits_for_approve_hosting(
    client: TestClient, site: HostedSite, operator: str
) -> None:
    """Hosting off, a staff verify approves no hosting; once the site hosts airlines the row
    waits under Approve hosting, labelled Verified (only a Desk verify says Desk)."""

    async def verified_without_hosting() -> str:
        held = await site.holder("RFC", verified=False)
        await accounts.decide(
            site.root,
            held.record.id,
            version=held.record.version,
            actor="operator:M. Tan#4f1c2a9b",
            verified=True,
            note=None,
            at=wall_clock_now(),
        )
        return held.record.id

    airline_id = site.run(client, verified_without_hosting)
    site.run(client, lambda: site.holder("RFB", hosting=False))
    listed = client.get("/api/admin/airlines").json()
    assert listed["to_approve"] == 2
    staff, desk = row_of(client, "RFC"), row_of(client, "RFB")
    assert (staff["status_label"], staff["hosting"]) == ("Verified", "desk")
    assert desk["status_label"] == "Verified (Desk)"
    one = client.get(f"/api/admin/airlines/{airline_id}").json()
    assert one["history"][-1]["actor"] == "operator:M. Tan#4f1c2a9b"
    approved = post(
        client, f"/api/admin/airlines/{airline_id}/approve-hosting", {"version": staff["version"]}
    )
    assert approved.json()["hosting"] == "operator"


def test_suspend_resume_and_delete_after_seven_days(
    client: TestClient, site: HostedSite, operator: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    held, member = site.run(client, lambda: site.airline("RFB", "shadow"))
    keyed = site.run(client, lambda: site.reg.create_key("RFB", "Ops", by="Ana Ops#" + member.id))
    key = keyed[1]
    held_cookie = site.cookie(held.login, held.record)
    suspended = post(client, "/api/admin/tenants/RFB/suspend", {"reason": "Unpaid checks"})
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["status"] == "suspended"
    assert suspended.json()["delete_after"] is not None
    handle = site.reg.handle("RFB")
    assert handle is not None
    assert handle.runtime is None

    operator_cookie = client.cookies[OPERATOR_COOKIE]
    client.cookies.clear()
    client.cookies.set(AIRLINE_COOKIE, held_cookie)
    assert client.get("/a/RFB/api/tenant/header").json()["suspended"]["reason"] == "Unpaid checks"
    write = client.post("/a/RFB/api/tenant/keys", json={"name": "More"})
    assert (write.status_code, error_of(write)) == (403, "tenant_suspended")
    assert error_of(httpx_push(client, "RFB", key, positions=[position()])) == "bad_key"
    client.cookies.clear()
    client.cookies.set(OPERATOR_COOKIE, operator_cookie)

    too_soon = post(client, "/api/admin/tenants/RFB/delete-data", {"confirm_icao": "RFB"})
    assert (too_soon.status_code, error_of(too_soon)) == (409, "too_soon")
    resumed = post(client, "/api/admin/tenants/RFB/resume")
    assert resumed.json()["status"] == "shadow"
    assert site.reg.handle("RFB").runtime is not None  # type: ignore[union-attr]
    post(client, "/api/admin/tenants/RFB/suspend", {"reason": "For good"})
    later = wall_clock_now() + timedelta(days=8)
    monkeypatch.setattr(routes_admin, "wall_clock_now", lambda: later)
    wrong = post(client, "/api/admin/tenants/RFB/delete-data", {"confirm_icao": "RFC"})
    assert (wrong.status_code, error_of(wrong)) == (422, "confirm_icao")
    deleting = post(client, "/api/admin/tenants/RFB/delete-data", {"confirm_icao": "RFB"})
    assert deleting.status_code == 200, deleting.text
    record = site.run(client, lambda: tenants.get_tenant(site.root, "RFB"))
    assert record is not None
    assert record.state in {"deleting", "deleted"}
    assert record.model_key is None


def test_the_ops_manager_invite_and_the_contact(
    client: TestClient, site: HostedSite, operator: str
) -> None:
    _, ana = site.run(client, lambda: site.airline("RFB", "setup"))
    refused = post(client, "/api/admin/tenants/RFB/ops-manager-invite")
    assert (refused.status_code, error_of(refused)) == (409, "already_member")
    # once the record holder is no member (another ops manager removed them), the operator's
    # invite to the holder's email is the way back in
    _, ola = site.run(
        client, lambda: site.person("RFB", "ops_manager", "ola@rfb.example", "Ola", by=ana)
    )

    async def holder_leaves() -> None:
        space = site.reg.space("RFB")
        at = wall_clock_now()
        await members.remove(
            site.root, "RFB", ana.id, by=ola, space=space, access=site.reg.access, at=at
        )
        await site.reg.reload("RFB")

    site.run(client, holder_leaves)
    invited = post(client, "/api/admin/tenants/RFB/ops-manager-invite")
    assert invited.status_code == 200, invited.text
    assert invited.json()["link"].startswith("http://testserver/join#")
    contact = client.get("/api/admin/tenants/RFB/contact").json()
    assert contact["ops_email"] == "ops@rfb.example"
    assert contact["mailto"].startswith("mailto:ops@rfb.example")
    assert client.get("/api/admin/tenants/RFZ/contact").status_code == 404
    assert client.get("/api/admin/tenants/rfb/contact").status_code == 404


def test_operators_invite_and_disable_never_the_last(client: TestClient, operator: str) -> None:
    listed = client.get("/api/admin/operators").json()
    assert [op["k"] for op in listed] == [operator]
    alone = post(client, f"/api/admin/operators/{operator}/disable")
    assert (alone.status_code, error_of(alone)) == (409, "last_operator")
    link = post(client, "/api/admin/operators/invites", {"name": "J. Lee", "email": "j@t.example"})
    assert link.status_code == 200, link.text
    mine = client.cookies[OPERATOR_COOKIE]
    client.cookies.clear()
    token = link.json()["link"].split("#", 1)[1]
    second = post(
        client,
        "/api/admin/invite/accept",
        {"token": token, "email": "j@t.example", "password": PASSWORD},
    )
    assert second.status_code == 200, second.text
    theirs = client.cookies[OPERATOR_COOKIE]
    client.cookies.set(OPERATOR_COOKIE, mine)
    k = second.json()["k"]
    disabled = post(client, f"/api/admin/operators/{k}/disable")
    assert disabled.status_code == 200, disabled.text
    assert any(op["disabled"] for op in disabled.json())
    client.cookies.set(OPERATOR_COOKIE, theirs)
    assert client.get("/api/admin/me").status_code == 401
    assert post(client, "/api/admin/operators/zzzz/disable").status_code == 401


def test_the_kill_switch_disables_an_operator(client: TestClient, operator: str) -> None:
    revoked = client.post(
        "/tasks/operator-revoke",
        json={"email": OPERATOR_EMAIL},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert revoked.status_code == 204, revoked.text
    assert client.get("/api/admin/me").status_code == 401
    again = client.post(
        "/tasks/operator-invite",
        json={"name": "M. Tan", "email": OPERATOR_EMAIL},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert again.status_code == 200, again.text
