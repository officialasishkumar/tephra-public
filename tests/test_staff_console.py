"""TEPHRA staff verify airlines on /admin, with hosting off as the live site runs it
(``TEPHRA_FEATURES=connect,onboard``): owner, 17 Oct 2026, "yes, do the split". The demo Desk is
RFA's dispatcher only, so a Desk PIN session never verifies, declines or deletes an airline. The
first staff account comes from the task token's one-time link; the list, one airline's answers
and private history, Verify, Decline with a reason and Delete record for a declined airline work
without hosting, and the hosting routes do not exist. Airlines the Desk decided before keep their
history as it was."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from test_airline_api import (
    ANSWERS,
    AT,
    EMAIL,
    PASSWORD,
    airline_settings,
    desk_login,
    docs,
    draft_body,
    error_of,
    ip,
    onboard,
    open_client,
    picture,
    put_docs,
    runtime_of,
    signup,
    submit,
)

from tephra.airline import accounts, passwords
from tephra.airline.models import AirlineAnswers
from tephra.api.auth import TASK_HEADER
from tephra.hosted.operators import COOKIE_NAME as OPERATOR_COOKIE
from tephra.store.base import Collection
from tephra.util.timeutil import FixedClock, use_clock

TASK_TOKEN = "staff-task-token-0123456789abcdef"
STAFF_EMAIL = "m.tan@tephra.example"


@pytest.fixture(autouse=True)
def fast_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)


def staff_client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, features: str
) -> Iterator[TestClient]:
    settings = airline_settings(tmp_path, features=features, task_token=TASK_TOKEN)
    with use_clock(FixedClock(AT)), open_client(settings, monkeypatch)() as c:
        yield c


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    yield from staff_client(tmp_path, monkeypatch, "connect,onboard")


def bootstrap(client: TestClient) -> str:
    """The first staff account from the task token's link (the hosting-off server's only way
    in), accepted: the client holds the staff cookie. Returns the account's short key."""
    minted = client.post(
        "/tasks/operator-invite",
        json={"name": "M. Tan", "email": STAFF_EMAIL},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert minted.status_code == 200, minted.text
    token = minted.json()["link"].split("#", 1)[1]
    accepted = client.post(
        "/api/admin/invite/accept",
        json={"token": token, "email": STAFF_EMAIL, "password": PASSWORD},
    )
    assert accepted.status_code == 200, accepted.text
    return str(accepted.json()["k"])


def two_airlines(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    first = onboard(client, headers=ip(60))
    second = onboard(client, email="b@rfa-ops.example", headers=ip(61))
    client.cookies.clear()
    return first, second


def post(client: TestClient, path: str, body: dict[str, Any]) -> httpx.Response:
    return client.post(path, json=body)


def stored(client: TestClient, airline_id: str) -> dict[str, Any]:
    return next(d for d in docs(client, Collection.AIRLINES) if d["id"] == airline_id)


# --- the console exists with onboard, hosting or not ------------------------------------


def test_without_onboard_the_staff_console_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for c in staff_client(tmp_path, monkeypatch, "connect"):
        minted = c.post(
            "/tasks/operator-invite",
            json={"name": "M. Tan", "email": STAFF_EMAIL},
            headers={TASK_HEADER: TASK_TOKEN},
        )
        answers = [c.get("/admin"), c.get("/admin/join"), c.get("/api/admin/me"), minted]
        assert [r.status_code for r in answers] == [404] * 4


def test_with_hosting_off_the_task_token_makes_the_first_staff_account(
    client: TestClient,
) -> None:
    page = client.get("/admin")
    assert page.status_code == 200
    assert page.headers["x-robots-tag"] == "noindex"
    assert client.get("/admin/join").status_code == 200
    assert client.get("/api/admin/me").status_code == 401
    # the nav asks /api/admin/me only for a staff cookie: other visitors' pages make no 401 request
    assert client.get("/api/airline/session").json()["staff"] is False
    no_token = post(client, "/tasks/operator-invite", {"name": "M. Tan", "email": STAFF_EMAIL})
    assert no_token.status_code == 403
    bootstrap(client)
    assert OPERATOR_COOKIE in client.cookies
    assert client.get("/api/airline/session").json()["staff"] is True
    forged = client.cookies[OPERATOR_COOKIE][:-2] + "xx"
    client.cookies.set(OPERATOR_COOKIE, forged)
    assert client.get("/api/airline/session").json()["staff"] is False
    client.cookies.delete(OPERATOR_COOKIE)
    client.post(
        "/api/admin/sign-in", json={"email": STAFF_EMAIL, "password": PASSWORD}
    ).raise_for_status()
    me = client.get("/api/admin/me").json()
    assert (me["name"], me["email"], me["you"]) == ("M. Tan", STAFF_EMAIL, True)
    again = client.post(
        "/tasks/operator-invite",
        json={"name": "J. Lee", "email": "j@tephra.example"},
        headers={TASK_HEADER: TASK_TOKEN},
    )
    assert (again.status_code, error_of(again)) == (409, "operators_exist")
    assert [op["name"] for op in client.get("/api/admin/operators").json()] == ["M. Tan"]


def test_with_hosting_off_staff_list_read_verify_decline_and_delete(client: TestClient) -> None:
    first, second = two_airlines(client)
    signup(client, email="draft@rfa.example", headers=ip(62))
    client.cookies.clear()
    bootstrap(client)

    listed = client.get("/api/admin/airlines").json()
    assert set(listed) == {"to_verify", "onboarding", "airlines"}
    assert (listed["to_verify"], listed["onboarding"]) == (2, 1)
    assert {a["id"] for a in listed["airlines"]} == {first["id"], second["id"]}
    # the console's words with hosting on or off: "Pending" beside To verify
    assert {a["status_label"] for a in listed["airlines"]} == {"Pending"}
    assert {a["decided_at"] for a in listed["airlines"]} == {None}
    one = client.get(f"/api/admin/airlines/{second['id']}").json()
    assert one["email"] == "b@rfa-ops.example"
    assert one["answers"]["airline"]["icao"] == ANSWERS["airline"]["icao"]
    assert [e["action"] for e in one["history"]] == ["created", "submitted"]
    assert one["history_ok"] is True

    stale = post(client, f"/api/admin/airlines/{first['id']}/verify", {"version": 99})
    assert (stale.status_code, error_of(stale)) == (409, "version_conflict")
    verified = post(
        client,
        f"/api/admin/airlines/{first['id']}/verify",
        {"version": first["version"], "note": "AOC checked"},
    )
    assert verified.status_code == 200, verified.text
    entry = verified.json()["history"][-1]
    assert verified.json()["status"] == "verified"
    assert verified.json()["decided_at"] is not None
    assert (entry["action"], entry["note"]) == ("verified", "AOC checked")
    assert entry["actor"].startswith("operator:M. Tan#")
    assert "hosting" not in stored(client, first["id"])  # nothing is hosted on this site
    again = post(client, f"/api/admin/airlines/{first['id']}/verify", {"version": 99})
    assert error_of(again) in {"version_conflict", "not_pending"}

    short = post(
        client, f"/api/admin/airlines/{second['id']}/decline", {"version": 2, "reason": "no"}
    )
    assert short.status_code == 422
    early = post(client, f"/api/admin/airlines/{second['id']}/delete", {"version": 2})
    assert (early.status_code, error_of(early)) == (409, "not_declined")
    declined = post(
        client,
        f"/api/admin/airlines/{second['id']}/decline",
        {"version": 2, "reason": "Not an airline we can find"},
    )
    assert declined.json()["status"] == "declined"
    assert stored(client, second["id"])["decline_reason"] == "Not an airline we can find"
    deleted = post(
        client,
        f"/api/admin/airlines/{second['id']}/delete",
        {"version": declined.json()["version"]},
    )
    assert deleted.status_code == 204
    assert second["id"] not in {d["id"] for d in docs(client, Collection.AIRLINES)}
    assert client.get(f"/api/admin/airlines/{second['id']}").status_code == 404


def test_with_hosting_off_a_draft_is_never_read_and_hosting_routes_do_not_exist(
    client: TestClient,
) -> None:
    draft = signup(client, email="draft@rfa.example", headers=ip(63)).json()["airline"]
    client.cookies.clear()
    bootstrap(client)
    assert client.get(f"/api/admin/airlines/{draft['id']}").status_code == 404
    verify = post(client, f"/api/admin/airlines/{draft['id']}/verify", {"version": 1})
    assert verify.status_code == 404
    hosting_only = [
        post(client, f"/api/admin/airlines/{draft['id']}/approve-hosting", {"version": 1}),
        post(client, "/api/admin/tenants/RFA/suspend", {"reason": "Testing"}),
        post(client, "/api/admin/tenants/RFA/resume", {}),
        post(client, "/api/admin/tenants/RFA/ops-manager-invite", {}),
        client.get("/api/admin/tenants/RFA/contact"),
    ]
    assert [r.status_code for r in hosting_only] == [404] * len(hosting_only)


# --- the Desk is RFA's dispatcher only --------------------------------------------------


def test_a_desk_pin_session_cannot_verify_decline_or_delete_an_airline(
    client: TestClient,
) -> None:
    first, second = two_airlines(client)
    before = [stored(client, first["id"]), stored(client, second["id"])]
    desk_login(client)
    assert client.get("/api/desk/me").status_code == 200
    staff_routes = [
        client.get("/api/admin/airlines"),
        client.get(f"/api/admin/airlines/{first['id']}"),
        post(client, f"/api/admin/airlines/{first['id']}/verify", {"version": 2}),
        post(
            client, f"/api/admin/airlines/{second['id']}/decline", {"version": 2, "reason": "x" * 9}
        ),
        post(client, f"/api/admin/airlines/{second['id']}/delete", {"version": 2}),
    ]
    assert [(r.status_code, error_of(r)) for r in staff_routes] == [(403, "operator_only")] * 5
    desk_routes = [
        client.get("/api/desk/airlines"),
        client.get("/api/desk/airlines/summary"),
        client.get(f"/api/desk/airlines/{first['id']}"),
        post(client, f"/api/desk/airlines/{first['id']}/verify", {"version": 2}),
        post(
            client, f"/api/desk/airlines/{second['id']}/decline", {"version": 2, "reason": "spam!"}
        ),
        post(client, f"/api/desk/airlines/{second['id']}/delete", {"version": 2}),
    ]
    assert {r.status_code for r in desk_routes} == {404}
    assert [stored(client, first["id"]), stored(client, second["id"])] == before


def test_a_desk_pin_session_cannot_verify_with_hosting_on_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.test_hosted_api import HostedSite

    site = HostedSite(tmp_path)
    with TestClient(site.app) as c:
        held = site.run(c, lambda: site.holder("RFB", verified=False))
        c.post("/api/desk/login", json={"name": "Ana K", "pin": "zulu-4711"})
        refused = c.post(f"/api/admin/airlines/{held.record.id}/verify", json={"version": 2})
        gone = c.post(f"/api/desk/airlines/{held.record.id}/verify", json={"version": 2})
        record = site.run(c, lambda: accounts.get_record(site.root, held.record.id))
    assert (refused.status_code, error_of(refused)) == (403, "operator_only")
    assert gone.status_code == 404
    assert record.status == "pending"


# --- existing data stays as it is -------------------------------------------------------


def test_an_airline_the_desk_decided_before_keeps_its_history(client: TestClient) -> None:
    store = runtime_of(client).store

    async def decided_at_the_desk() -> str:
        record, _ = await accounts.create_account(
            store, email=EMAIL, password_hash="x", recovery_sha256="0" * 64, at=AT
        )
        model = AirlineAnswers.model_validate(ANSWERS)
        record = await accounts.submit(
            store, record.id, version=record.version, answers=model, flags=[], at=AT
        )
        await accounts.decide(
            store,
            record.id,
            version=record.version,
            actor="desk:Ana K",
            verified=True,
            note="Checked by phone",
            at=AT,
        )
        return record.id

    airline_id = client.portal.call(decided_at_the_desk)  # type: ignore[union-attr]
    bootstrap(client)
    listed = client.get("/api/admin/airlines").json()
    assert [(a["id"], a["status"]) for a in listed["airlines"]] == [(airline_id, "verified")]
    history = client.get(f"/api/admin/airlines/{airline_id}").json()["history"]
    assert (history[-1]["actor"], history[-1]["note"]) == ("desk:Ana K", "Checked by phone")


def test_flags_and_a_broken_history_link_are_said(client: TestClient) -> None:
    gmail = {**ANSWERS, "airline": {**ANSWERS["airline"], "aoc_number": None}}
    gmail["airline"]["ops_email"] = "ops@" + "gmail.com"
    view = onboard(client, email="desk@rfa-ops.example", body_answers=gmail, headers=ip(64))
    [record] = docs(client, Collection.AIRLINES)
    client.cookies.clear()
    bootstrap(client)
    flags = client.get(f"/api/admin/airlines/{view['id']}").json()["flags"]
    assert "contact email domain is a public mail provider" in flags
    assert "account email domain differs from the operations email's" in flags
    assert "no AOC number given" in flags
    record["history"][0]["note"] = "rewritten"
    put_docs(client, Collection.AIRLINES, {view["id"]: record})
    body = client.get(f"/api/admin/airlines/{view['id']}").json()
    assert (body["history_ok"], body["history_broken_at"]) == (False, 1)


def test_nothing_an_airline_or_staff_do_here_is_published(client: TestClient) -> None:
    bootstrap(client)
    before = picture(client)
    first = signup(client, headers=ip(90)).json()["airline"]
    steps = [
        client.put("/api/airline/draft", json=draft_body(1, airline={"name": "Ring of Fire"})),
        submit(client, version=2),
        client.put("/api/airline/answers", json={"version": 3, "answers": ANSWERS}),
        client.put(
            "/api/airline/assistant", json={"version": 4, "assistant": {"provider": "none"}}
        ),
        client.post(
            "/api/airline/feeds/dry-run",
            json={"format": "tephra.airline/1", "positions": [{"hex": "8a0412"}]},
        ),
    ]
    second = onboard(client, email="b@rfa.example", headers=ip(91))
    steps += [
        post(client, f"/api/admin/airlines/{first['id']}/verify", {"version": 5}),
        post(
            client,
            f"/api/admin/airlines/{second['id']}/decline",
            {"version": 2, "reason": "not real"},
        ),
        post(client, f"/api/admin/airlines/{second['id']}/delete", {"version": 3}),
    ]
    after = picture(client)

    assert [r.status_code for r in steps] == [200] * 7 + [204]
    assert [d["id"] for d in docs(client, Collection.AIRLINES)] == [first["id"]]
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)
