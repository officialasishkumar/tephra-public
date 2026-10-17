"""Airline accounts over HTTP: onboarding's account (a draft first, then Review submits it),
sign-in limits, recovery, the private workspace and the Desk's review. No network and no model:
a real runtime on fixture feeds that never ticks, so the shared picture can be compared byte for
byte before and after.
"""

import copy
import json
import re
import unicodedata
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_pipeline import AT, FixtureSource, make_runtime, make_settings

from tephra.airline import accounts, passwords
from tephra.airline.models import AirlineAnswers, AirlineRecord, OnboardDraft
from tephra.airline.sessions import COOKIE_NAME
from tephra.api import server
from tephra.api.auth import COOKIE_NAME as DESK_COOKIE
from tephra.api.auth import sign_session, wall_clock_now
from tephra.config import Settings
from tephra.models import SseEvent
from tephra.pipeline import Runtime
from tephra.store.base import Collection
from tephra.util.timeutil import FixedClock, use_clock

PIN = "4321"
SECRET = "test-session-secret-0123456789abcdef"
EMAIL = "ops@rfa.example"
PASSWORD = "correct horse battery staple"
FIXTURE = Path(__file__).parent / "fixtures" / "airline" / "answers.json"
ANSWERS: dict[str, Any] = json.loads(FIXTURE.read_text())
RECOVERY_CODE = re.compile(r"^[A-Z0-9]{4}(-[A-Z0-9]{4}){3}$")
ACCOUNT_ROUTES = [
    ("POST", "/api/airline/accounts"),
    ("PUT", "/api/airline/draft"),
    ("POST", "/api/airline/submit"),
    ("POST", "/api/airline/sign-in"),
    ("POST", "/api/airline/recover"),
    ("POST", "/api/airline/sign-out"),
    ("GET", "/api/airline/me"),
    ("PUT", "/api/airline/answers"),
    ("PUT", "/api/airline/assistant"),
    ("POST", "/api/airline/delete"),
    ("POST", "/api/airline/feeds/dry-run"),
]
DESK_ROUTES = [
    ("GET", "/api/desk/airlines"),
    ("GET", "/api/desk/airlines/summary"),
    ("GET", "/api/desk/airlines/AL-0123456789ab"),
    ("POST", "/api/desk/airlines/AL-0123456789ab/verify"),
    ("POST", "/api/desk/airlines/AL-0123456789ab/decline"),
    ("POST", "/api/desk/airlines/AL-0123456789ab/delete"),
]


# --- harness ----------------------------------------------------------------------------


@pytest.fixture
def fast_scrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cheap scrypt cost for tests that sign in many times (the stored string records it)."""
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)


def airline_settings(tmp_path: Path, **changes: Any) -> Settings:
    return make_settings(
        tmp_path,
        desk_pin=SecretStr(PIN),
        session_secret=SecretStr(SECRET),
        local_scheduler=False,
        **changes,
    )


def open_client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Callable[[], TestClient]:
    async def no_tick(_: Runtime) -> None:
        return None

    async def factory(given: Settings) -> Runtime:
        return make_runtime(given, FixtureSource())

    monkeypatch.setattr(server, "_startup_tick", no_tick)
    return lambda: TestClient(server.create_app(settings, runtime_factory=factory))


@pytest.fixture
def client(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast_scrypt: None
) -> Iterator[TestClient]:
    with use_clock(FixedClock(AT)), open_client(airline_settings(tmp_path), monkeypatch)() as c:
        yield c


def runtime_of(client: TestClient) -> Runtime:
    runtime: Runtime = client.app.state.runtime  # type: ignore[attr-defined]
    return runtime


def answers(**paths: Any) -> dict[str, Any]:
    """The fixture answers with ``a__b__0__c=value`` set (``a.b.0.c``)."""
    data = copy.deepcopy(ANSWERS)
    for path, value in paths.items():
        *parents, last = path.split("__")
        node: Any = data
        for part in parents:
            node = node[int(part)] if isinstance(node, list) else node[part]
        node[int(last) if isinstance(node, list) else last] = value
    return data


def ip(n: int) -> dict[str, str]:
    return {"X-Forwarded-For": f"203.0.113.{n}"}


def signup(
    client: TestClient,
    *,
    email: str = EMAIL,
    password: str = PASSWORD,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> httpx.Response:
    """The account alone: its onboarding is a draft."""
    body = {"email": email, "password": password, "acknowledge": True, **extra}
    return client.post("/api/airline/accounts", json=body, headers=headers or ip(1))


def version_of(client: TestClient) -> int:
    return int(client.get("/api/airline/me").json()["version"])


def submit(
    client: TestClient, body_answers: dict[str, Any] | None = None, *, version: int | None = None
) -> httpx.Response:
    body = {
        "version": version_of(client) if version is None else version,
        "answers": ANSWERS if body_answers is None else body_answers,
    }
    return client.post("/api/airline/submit", json=body)


def onboard(
    client: TestClient,
    *,
    email: str = EMAIL,
    body_answers: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """An account whose answers are submitted: the airline's view, pending verification."""
    created = signup(client, email=email, headers=headers)
    assert created.status_code == 201, created.text
    submitted = submit(client, body_answers, version=created.json()["airline"]["version"])
    assert submitted.status_code == 200, submitted.text
    view: dict[str, Any] = submitted.json()
    return view


def draft_body(version: int, at: str = "fleet", **values: Any) -> dict[str, Any]:
    return {"version": version, "draft": {"at": at, "seen": ["airline", at], "values": values}}


def sign_in(
    client: TestClient, password: str = PASSWORD, *, email: str = EMAIL, n: int = 50
) -> httpx.Response:
    return client.post(
        "/api/airline/sign-in", json={"email": email, "password": password}, headers=ip(n)
    )


def desk_login(client: TestClient) -> None:
    response = client.post("/api/desk/login", json={"name": "Ana K", "pin": PIN})
    assert response.status_code == 200


def error_of(response: httpx.Response) -> str:
    return str(response.json()["error"])


async def stored(client: TestClient, collection: Collection) -> list[dict[str, Any]]:
    return await runtime_of(client).store.list_docs(collection, limit=2000)


def docs(client: TestClient, collection: Collection) -> list[dict[str, Any]]:
    return client.portal.call(stored, client, collection)  # type: ignore[union-attr]


def put_docs(client: TestClient, collection: Collection, rows: dict[str, dict[str, Any]]) -> None:
    async def write() -> None:
        for doc_id, doc in rows.items():
            await runtime_of(client).store.put(collection, doc_id, doc)

    client.portal.call(write)  # type: ignore[union-attr]


def request(client: TestClient, method: str, path: str, **kwargs: Any) -> httpx.Response:
    if method in {"POST", "PUT"}:
        kwargs.setdefault("json", {})
    return client.request(method, path, **kwargs)


# --- create -----------------------------------------------------------------------------


def test_creating_an_account_keeps_a_hash_a_draft_record_and_signs_in(
    client: TestClient,
) -> None:
    response = signup(client)

    assert response.status_code == 201
    body = response.json()
    assert RECOVERY_CODE.fullmatch(body["recovery_code"])
    view = body["airline"]
    assert (view["status"], view["status_label"]) == ("draft", "Not submitted")
    assert (view["editable"], view["steps"], view["answers"]) == (False, [], None)
    assert view["submitted_at"] is None
    assert view["draft"] == {"at": None, "seen": [], "values": OnboardDraft().values.model_dump()}
    assert {"flags", "history", "login_key"}.isdisjoint(view)
    assert COOKIE_NAME in response.cookies
    [login] = docs(client, Collection.AIRLINE_LOGINS)
    [record] = docs(client, Collection.AIRLINES)
    assert login["password"].startswith("scrypt$")
    assert PASSWORD not in json.dumps(login)
    assert body["recovery_code"] not in json.dumps(login)
    assert login["recovery_sha256"] == passwords.code_sha256(body["recovery_code"])
    assert record["status"] == "draft"
    assert [entry["action"] for entry in record["history"]] == ["created"]
    assert record["history"][0]["actor"] == "airline"
    created = datetime.fromisoformat(record["created_at"])
    assert abs((created - datetime.now(UTC)).total_seconds()) < 120  # wall clock, not AT
    assert record["flags"] == []
    session = client.get("/api/airline/session").json()
    assert session == {
        "accounts": True,
        "signed_in": True,
        "icao": None,
        "name": None,
        "status": None,
    }


def test_submitting_checks_the_answers_and_waits_for_a_dispatcher(client: TestClient) -> None:
    created = signup(client).json()["airline"]
    response = submit(client, version=created["version"])

    assert response.status_code == 200
    view = response.json()
    assert (view["status"], view["status_label"]) == ("pending", "Pending verification")
    assert view["editable"] is True
    assert view["draft"] is None
    assert view["answers"]["airline"]["name"] == "Ring of Fire Air"
    assert [step["kind"] for step in view["steps"]] == ["submitted"]
    assert COOKIE_NAME in response.cookies
    [record] = docs(client, Collection.AIRLINES)
    assert record["draft"] is None
    assert [entry["action"] for entry in record["history"]] == ["created", "submitted"]
    submitted = datetime.fromisoformat(record["submitted_at"])
    assert abs((submitted - datetime.now(UTC)).total_seconds()) < 120
    assert "no AOC number given" not in record["flags"]
    assert accounts.verify_history(AirlineRecord.model_validate(record).history) is None
    session = client.get("/api/airline/session").json()
    assert (session["icao"], session["name"]) == ("RFA", "Ring of Fire Air")
    again = submit(client)
    assert (again.status_code, error_of(again)) == (409, "already_submitted")
    late = client.put("/api/airline/draft", json=draft_body(view["version"]))
    assert (late.status_code, error_of(late)) == (409, "already_submitted")


def test_a_draft_saves_the_pages_as_typed(client: TestClient) -> None:
    version = signup(client).json()["airline"]["version"]
    typed = {
        "airline": {"name": "Ring\tof Fire", "icao": "RF", "callsign_touched": True},
        "fleet": {"aircraft": [{"registration": "PK-RFA", "seats": 180, "hex": "zz"}]},
        "policy": {"changes": {"exposure.vertical_margin_ft": {"value": "x", "base": 2000}}},
        "network": {"airports": ["WADD"], "alternates": {"WADD": ["WIII"]}},
    }
    saved = client.put("/api/airline/draft", json=draft_body(version, **typed))
    stale = client.put("/api/airline/draft", json=draft_body(version, **typed))

    assert saved.status_code == 200, saved.text
    draft = saved.json()["draft"]
    assert draft["at"] == "fleet"
    assert draft["seen"] == ["airline", "fleet"]
    values = draft["values"]
    assert values["airline"]["name"] == "Ring of Fire"  # the tab, a control character, a space
    assert values["airline"]["icao"] == "RF"  # kept as typed: submit checks it
    assert values["fleet"]["aircraft"][0]["seats"] == "180"
    assert values["policy"]["changes"]["exposure.vertical_margin_ft"]["value"] == "x"
    assert (stale.status_code, error_of(stale)) == (409, "version_conflict")
    me = client.get("/api/airline/me").json()
    assert me["draft"] == draft
    [record] = docs(client, Collection.AIRLINES)
    assert [e["action"] for e in record["history"]] == ["created", "answers_changed"]


@pytest.mark.parametrize(
    "values",
    [
        {"airline": {"password": "x"}},
        {"fleet": {"aircraft": [{"registration": "x" * 400}]}},
        {"people": {"dispatchers": [{"name": "A", "role": "owner"}]}},
        {"secrets": {}},
    ],
)
def test_a_draft_holds_only_the_pages_keys_and_bounded_values(
    client: TestClient, values: dict[str, Any]
) -> None:
    version = signup(client).json()["airline"]["version"]
    response = client.put("/api/airline/draft", json=draft_body(version, **values))
    assert (response.status_code, error_of(response)) == (422, "validation_failed")
    assert client.get("/api/airline/me").json()["version"] == version


def test_a_draft_cannot_use_the_submitted_airlines_routes(client: TestClient) -> None:
    version = signup(client).json()["airline"]["version"]
    edit = client.put("/api/airline/answers", json={"version": version, "answers": ANSWERS})
    model = client.put(
        "/api/airline/assistant", json={"version": version, "assistant": {"provider": "none"}}
    )

    for refused in (edit, model):
        assert (refused.status_code, error_of(refused)) == (403, "answers_locked")
        assert refused.json()["detail"] == "Submit your onboarding first."


def test_sign_in_says_the_accounts_status(client: TestClient) -> None:
    assert signup(client).status_code == 201
    client.cookies.clear()
    draft = sign_in(client).json()
    assert submit(client).status_code == 200
    client.cookies.clear()
    pending = sign_in(client, n=51).json()

    assert (draft["status"], draft["icao"], draft["name"]) == ("draft", None, None)
    assert (pending["status"], pending["icao"]) == ("pending", "RFA")


def test_a_record_stored_before_drafts_keeps_its_status(client: TestClient) -> None:
    """Records written by the first onboarding build have answers, a status and no draft."""
    view = onboard(client)
    [record] = docs(client, Collection.AIRLINES)
    for key in ("draft", "created_at"):
        record.pop(key)
    record["history"] = record["history"][:1]
    put_docs(client, Collection.AIRLINES, {view["id"]: record})

    me = client.get("/api/airline/me")
    assert me.status_code == 200
    assert (me.json()["status"], me.json()["draft"]) == ("pending", None)
    assert me.json()["answers"]["airline"]["icao"] == "RFA"


def test_the_stored_hash_uses_owasps_scrypt_cost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with use_clock(FixedClock(AT)), open_client(airline_settings(tmp_path), monkeypatch)() as c:
        assert signup(c).status_code == 201
        [login] = docs(c, Collection.AIRLINE_LOGINS)
    assert login["password"].startswith("scrypt$16384$8$5$")


def test_the_answers_hold_no_secret_field() -> None:
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            names.update(node.get("properties", {}))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(AirlineAnswers.model_json_schema())
    assert "registration" in names
    assert not [n for n in names if re.search(r"pin|secret|token|password|key|url|address", n)]


@pytest.mark.parametrize(
    ("body_answers", "where"),
    [
        (answers(airline__icao="R1"), "answers.airline.icao"),
        (
            answers(
                fleet__aircraft=[
                    {"registration": f"PK-{i:04d}", "type_icao": "A320", "seats": 180}
                    for i in range(1001)
                ]
            ),
            "answers.fleet.aircraft",
        ),
        (answers(fleet__aircraft__2__hex="8a0412"), "answers.fleet"),
        (
            answers(policy__changes=[{"name": "planner.made_up", "value": 5, "reason": "why"}]),
            "answers.policy.changes.0.name",
        ),
        (
            answers(
                policy__changes=[{"name": "recovery.max_fdp_min", "value": 600, "reason": "why"}]
            ),
            "answers.policy.changes.0.name",
        ),
        (
            answers(
                policy__changes=[
                    {"name": "planner.divert_within_min", "value": 99_000, "reason": "why"}
                ]
            ),
            "answers.policy.changes",
        ),
        (answers(policy__sra_ref=None), "answers.policy"),
        (
            answers(people__dispatchers=[{"name": "Ana K", "role": "views"}]),
            "answers.people",
        ),
        (
            answers(
                assistant={"provider": "gemini", "model": "gemma4:e4b", "model_lite": "gemma4:e4b"}
            ),
            "answers.assistant",
        ),
        (answers(airline__name="Ring\u0007of Fire"), "answers.airline.name"),
        (answers(people__dispatchers__0__name="A"), "answers.people.dispatchers.0.name"),
        (answers(fleet__extra_prefixes=["RFA"]), "answers: Value error, an extra callsign"),
    ],
)
def test_bad_answers_are_refused_by_location_without_echoing_them(
    client: TestClient, body_answers: dict[str, Any], where: str
) -> None:
    assert signup(client).status_code == 201
    response = submit(client, body_answers)

    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_failed"
    assert any(problem.startswith(f"{where}") for problem in body["problems"]), body["problems"]
    assert EMAIL not in response.text
    assert PASSWORD not in response.text
    [record] = docs(client, Collection.AIRLINES)
    assert (record["status"], record["answers"]) == ("draft", None)


def test_the_honeypot_and_the_acknowledgement_are_checked(client: TestClient) -> None:
    filled = signup(client, website="https://spam.example")
    unticked = signup(client, acknowledge=False)
    same = signup(client, password=EMAIL.upper())

    assert (filled.status_code, unticked.status_code) == (422, 422)
    assert any(p.startswith("website") for p in filled.json()["problems"])
    assert same.status_code == 422
    assert EMAIL not in same.text
    assert docs(client, Collection.AIRLINES) == []


def test_the_same_email_twice_is_refused_and_leaves_one_airline(client: TestClient) -> None:
    assert signup(client).status_code == 201
    again = signup(client, email=EMAIL.upper(), headers=ip(2))

    assert again.status_code == 409
    assert error_of(again) == "email_taken"
    assert again.json()["detail"] == "An account with this email exists. Sign in instead."
    assert len(docs(client, Collection.AIRLINES)) == 1


def test_a_lost_race_on_the_email_leaves_no_record(client: TestClient) -> None:
    key = accounts.login_key(EMAIL)
    put_docs(client, Collection.AIRLINE_LOGINS, {key: {"login_key": key}})

    response = signup(client)

    assert response.status_code == 409
    assert docs(client, Collection.AIRLINES) == []


def test_bodies_over_128_kib_are_refused(client: TestClient) -> None:
    padded = {"email": EMAIL, "password": PASSWORD, "acknowledge": True, "pad": "x" * 140_000}
    assert client.post("/api/airline/accounts", json=padded, headers=ip(1)).status_code == 413
    version = signup(client).json()["airline"]["version"]
    big = answers(airline__contact_name="x" * 140_000)
    assert submit(client, big, version=version).status_code == 413
    huge = draft_body(version, airline={"contact_name": "x" * 140_000})
    assert client.put("/api/airline/draft", json=huge).status_code == 413


def test_a_thousand_aircraft_draft_fits_the_onboarding_body_limit(client: TestClient) -> None:
    """Bigger than the 16 KiB every other route takes: the draft route has onboarding's 128."""
    version = signup(client).json()["airline"]["version"]
    rows = [
        {"registration": f"PK-{n:04d}", "type_icao": "A320", "seats": "180", "hex": f"8a{n:04x}"}
        for n in range(1000)
    ]
    response = client.put("/api/airline/draft", json=draft_body(version, fleet={"aircraft": rows}))
    assert response.status_code == 200, response.status_code


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_site_requests_are_refused(client: TestClient, headers: dict[str, str]) -> None:
    body = {"email": EMAIL, "password": PASSWORD, "acknowledge": True}
    response = client.post("/api/airline/accounts", json=body, headers={**ip(1), **headers})
    assert response.status_code == 403
    version = signup(client).json()["airline"]["version"]
    saves = [
        client.put("/api/airline/draft", json=draft_body(version), headers=headers),
        client.post(
            "/api/airline/submit", json={"version": version, "answers": ANSWERS}, headers=headers
        ),
    ]
    assert [r.status_code for r in saves] == [403, 403]
    assert client.get("/api/airline/me").json()["version"] == version


def test_a_form_post_without_the_header_is_refused(client: TestClient) -> None:
    response = client.post(
        "/api/airline/accounts",
        content=json.dumps({"email": EMAIL}),
        headers={**ip(1), "Content-Type": "text/plain"},
    )
    assert response.status_code == 403


def test_signups_are_limited_per_address_and_per_day(client: TestClient) -> None:
    made = [signup(client, email=f"ops{i}@rfa.example", headers=ip(9)) for i in range(4)]
    other = signup(client, email="ops9@rfa.example", headers=ip(10))

    assert [r.status_code for r in made] == [201, 201, 201, 429]
    assert error_of(made[3]) == "too_many_requests"
    assert int(made[3].headers["Retry-After"]) > 0
    assert other.status_code == 201


def test_attempts_are_limited_per_address_before_any_validation(client: TestClient) -> None:
    tries = [signup(client, email="not an email", headers=ip(7)) for _ in range(11)]
    other = signup(client, email="not an email", headers=ip(8))

    assert [r.status_code for r in tries] == [422] * 10 + [429]
    assert "Retry-After" in tries[10].headers
    assert other.status_code == 422


def test_thirty_accepted_signups_a_day_across_addresses(client: TestClient) -> None:
    codes = [
        signup(client, email=f"ops{i}@rfa.example", headers=ip(100 + i // 3)).status_code
        for i in range(31)
    ]
    assert codes == [201] * 30 + [429]


def test_full_onboarding_answers_503_and_invalid_bodies_never_count(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[bool] = []
    real = accounts.onboarding_full

    async def spy(store: Any) -> bool:
        asked.append(True)
        return await real(store)

    monkeypatch.setattr(accounts, "onboarding_full", spy)
    assert signup(client, email="R").status_code == 422
    assert asked == []
    put_docs(
        client,
        Collection.AIRLINES,
        {f"AL-{i:012x}": {"status": "pending", "submitted_at": "x"} for i in range(200)},
    )
    full = signup(client)
    assert full.status_code == 503
    assert error_of(full) == "onboarding_full"
    assert asked == [True]


def test_two_hundred_pending_airlines_pause_submitting(client: TestClient) -> None:
    assert signup(client).status_code == 201
    put_docs(
        client,
        Collection.AIRLINES,
        {f"AL-{i:012x}": {"status": "pending", "submitted_at": "x"} for i in range(200)},
    )
    paused = submit(client)
    assert (paused.status_code, error_of(paused)) == (503, "onboarding_full")
    assert client.get("/api/airline/me").json()["status"] == "draft"


def test_three_hundred_drafts_answer_503(client: TestClient) -> None:
    put_docs(client, Collection.AIRLINES, {f"AL-{i:012x}": {"status": "draft"} for i in range(300)})
    assert error_of(signup(client)) == "onboarding_full"


def test_a_thousand_stored_airlines_answer_503(client: TestClient) -> None:
    put_docs(client, Collection.AIRLINE_LOGINS, {f"{i:064x}": {"x": i} for i in range(1000)})
    assert error_of(signup(client)) == "onboarding_full"


# --- sign in ----------------------------------------------------------------------------


def test_sign_in_answers_the_same_for_a_wrong_password_and_an_unknown_email(
    client: TestClient,
) -> None:
    assert signup(client).status_code == 201
    client.cookies.clear()
    known = [sign_in(client, "wrong password!", n=20) for _ in range(6)]
    unknown = [sign_in(client, "wrong password!", email="no@one.example", n=21) for _ in range(6)]

    for runs in (known, unknown):
        assert [r.status_code for r in runs] == [401] * 5 + [429]
        assert [r.headers.get("X-Tephra-Tries-Left") for r in runs[:5]] == ["4", "3", "2", "1", "0"]
        assert runs[0].json() == {
            "error": "bad_credentials",
            "detail": "That email and password don't match",
            "problems": [],
            "current": None,
        }
        assert "Retry-After" in runs[5].headers
    good = sign_in(client, n=22)
    assert good.status_code == 200
    assert good.json()["signed_in"] is True
    assert COOKIE_NAME in good.cookies


def test_a_password_typed_decomposed_signs_in(client: TestClient) -> None:
    password = unicodedata.normalize("NFC", "Ćrêpe sûzette dé jour")
    assert signup(client, password=password).status_code == 201
    client.cookies.clear()
    assert sign_in(client, unicodedata.normalize("NFD", password)).status_code == 200


def test_guessing_one_email_from_many_addresses_stops_at_ten(client: TestClient) -> None:
    created = signup(client).json()
    client.cookies.clear()
    first = [sign_in(client, "wrong password!", n=30) for _ in range(5)]
    second = [sign_in(client, "wrong password!", n=31) for _ in range(5)]
    blocked = sign_in(client, n=32)

    assert [r.status_code for r in first + second] == [401] * 10
    assert second[-1].headers["X-Tephra-Tries-Left"] == "0"
    assert blocked.status_code == 429
    recovered = client.post(
        "/api/airline/recover",
        json={
            "email": EMAIL,
            "recovery_code": created["recovery_code"].lower().replace("-", ""),
            "new_password": "a new long password",
        },
        headers=ip(33),
    )
    assert recovered.status_code == 200


def test_two_addresses_in_one_ipv6_64_share_a_throttle(client: TestClient) -> None:
    def from_(address: str) -> int:
        return client.post(
            "/api/airline/sign-in",
            json={"email": "no@one.example", "password": "x"},
            headers={"X-Forwarded-For": address},
        ).status_code

    codes = [from_(f"2001:db8:1:2::{i % 2 + 1}") for i in range(5)]
    assert codes == [401] * 5
    assert from_("2001:db8:1:2::99") == 429
    assert from_("2001:db8:1:3::1") == 401


def test_signing_in_to_ones_own_account_never_resets_the_address_limit(
    client: TestClient,
) -> None:
    """The address limit is shared across emails: a success clears only its own email's
    count, so an attacker's own account cannot reset guessing at other emails."""
    assert signup(client, email="mine@rfa.example").status_code == 201
    client.cookies.clear()
    codes = []
    for victim in range(8):
        codes.append(sign_in(client, "wrong password!", email=f"v{victim}@x.example", n=70))
        if victim % 2 == 1:
            assert sign_in(client, email="mine@rfa.example", n=70).status_code in {200, 429}
    assert [r.status_code for r in codes] == [401] * 5 + [429] * 3


def test_a_success_clears_that_emails_count(client: TestClient) -> None:
    assert signup(client).status_code == 201
    client.cookies.clear()
    for n in range(9):
        assert sign_in(client, "wrong password!", n=100 + n).status_code == 401
    assert sign_in(client, n=120).status_code == 200
    again = [sign_in(client, "wrong password!", n=130 + n).status_code for n in range(9)]
    assert again == [401] * 9  # without the clear, the email's tenth failure blocks the next


def test_deeply_nested_json_is_refused_as_not_json(client: TestClient) -> None:
    body = "[" * 60_000 + "]" * 60_000
    response = client.post(
        "/api/airline/accounts",
        content=body,
        headers={"content-type": "application/json", **ip(3)},
    )
    assert (response.status_code, error_of(response)) == (422, "validation_failed")
    assert response.json()["problems"] == ["body: not JSON"]


def test_recovery_sets_a_new_password_and_code_and_signs_other_browsers_out(
    client: TestClient,
) -> None:
    created = signup(client).json()
    old_cookie = client.cookies[COOKIE_NAME]
    wrong = client.post(
        "/api/airline/recover",
        json={"email": EMAIL, "recovery_code": "AAAA-BBBB-CCCC-DDDD", "new_password": "x" * 12},
        headers=ip(40),
    )
    assert (wrong.status_code, error_of(wrong)) == (401, "bad_credentials")
    assert wrong.json()["detail"] == "That email and recovery code don't match"
    response = client.post(
        "/api/airline/recover",
        json={
            "email": EMAIL,
            "recovery_code": created["recovery_code"],
            "new_password": "a brand new password",
        },
        headers=ip(41),
    )

    assert response.status_code == 200
    new_code = response.json()["recovery_code"]
    assert RECOVERY_CODE.fullmatch(new_code)
    assert new_code != created["recovery_code"]
    assert client.get("/api/airline/me").status_code == 200
    client.cookies.set(COOKIE_NAME, old_cookie)
    assert client.get("/api/airline/me").status_code == 401
    client.cookies.clear()
    assert sign_in(client).status_code == 401
    assert sign_in(client, "a brand new password", n=51).status_code == 200
    reused = client.post(
        "/api/airline/recover",
        json={"email": EMAIL, "recovery_code": created["recovery_code"], "new_password": "y" * 12},
        headers=ip(42),
    )
    assert reused.status_code == 401


# --- the workspace ----------------------------------------------------------------------


def test_answers_change_while_pending_and_the_cookie_follows_a_new_name(
    client: TestClient,
) -> None:
    view = onboard(client)
    renamed = answers(airline__name="Ring of Fire Airways")
    stale = client.put("/api/airline/answers", json={"version": 9, "answers": renamed})
    response = client.put(
        "/api/airline/answers", json={"version": view["version"], "answers": renamed}
    )

    assert (stale.status_code, error_of(stale)) == (409, "version_conflict")
    assert response.status_code == 200
    assert COOKIE_NAME in response.cookies
    assert response.json()["version"] == view["version"] + 1
    assert client.get("/api/airline/session").json()["name"] == "Ring of Fire Airways"
    [record] = docs(client, Collection.AIRLINES)
    assert [e["action"] for e in record["history"]] == ["created", "submitted", "answers_changed"]
    same = client.put(
        "/api/airline/answers", json={"version": view["version"] + 1, "answers": renamed}
    )
    assert same.status_code == 200
    assert COOKIE_NAME not in same.cookies


def test_verified_answers_are_locked_and_the_assistant_changes_in_every_status(
    client: TestClient,
) -> None:
    view = onboard(client)
    desk_login(client)
    verified = client.post(
        f"/api/desk/airlines/{view['id']}/verify", json={"version": view["version"]}
    )
    assert verified.status_code == 200
    me = client.get("/api/airline/me").json()
    locked = client.put("/api/airline/answers", json={"version": me["version"], "answers": ANSWERS})
    choice = {
        "provider": "gemini",
        "model": "gemma-4-31b-it",
        "model_lite": "gemini-3.5-flash-lite",
    }
    changed = client.put(
        "/api/airline/assistant", json={"version": me["version"], "assistant": choice}
    )

    assert me["status_label"] == "Verified"
    assert me["editable"] is False
    assert [step["kind"] for step in me["steps"]] == ["submitted", "verified"]
    assert (locked.status_code, error_of(locked)) == (403, "answers_locked")
    assert locked.json()["detail"] == (
        "Your answers are kept as verified. Ask a TEPHRA dispatcher to change them."
    )
    assert changed.status_code == 200
    assert changed.json()["answers"]["assistant"] == choice
    stale = client.put(
        "/api/airline/assistant", json={"version": me["version"], "assistant": choice}
    )
    assert stale.status_code == 409


def test_deleting_the_account_needs_the_password_and_removes_both_documents(
    client: TestClient,
) -> None:
    assert signup(client).status_code == 201
    wrong = client.post("/api/airline/delete", json={"password": "not it at all"}, headers=ip(60))
    assert (wrong.status_code, error_of(wrong)) == (401, "bad_credentials")
    gone = client.post("/api/airline/delete", json={"password": PASSWORD}, headers=ip(60))

    assert gone.status_code == 204
    assert docs(client, Collection.AIRLINES) == []
    assert docs(client, Collection.AIRLINE_LOGINS) == []
    assert client.get("/api/airline/me").status_code == 401
    assert client.get("/api/airline/session").json()["signed_in"] is False


def test_signing_out_clears_the_cookie(client: TestClient) -> None:
    assert signup(client).status_code == 201
    out = client.post("/api/airline/sign-out", json={})
    assert out.status_code == 204
    assert client.get("/api/airline/me").status_code == 401


def test_signing_out_ends_the_session_on_the_server(client: TestClient) -> None:
    assert signup(client).status_code == 201
    copied = client.cookies[COOKIE_NAME]
    assert client.post("/api/airline/sign-out", json={}).status_code == 204
    client.cookies.set(COOKIE_NAME, copied)

    assert client.get("/api/airline/me").status_code == 401
    assert client.post("/api/airline/sign-out", json={}).status_code == 204  # stale: no change
    [login] = docs(client, Collection.AIRLINE_LOGINS)
    assert login["session_version"] == 2
    client.cookies.clear()
    assert sign_in(client).status_code == 200
    assert client.get("/api/airline/me").status_code == 200


def test_saves_are_limited_and_never_grow_the_history_without_bound(
    client: TestClient,
) -> None:
    """100 saves a day per airline (batch 2 security finding 4): a walk through the nine pages
    with many edits fits, and one cookie cannot spend the store's free daily writes."""
    roomy = server.LoginThrottle(max_failures=10_000, window_s=300.0)
    client.app.state.airline_requests = roomy  # type: ignore[attr-defined]
    version = signup(client).json()["airline"]["version"]
    codes = []
    for n in range(101):
        if n < 50:
            r = client.put("/api/airline/draft", json=draft_body(version))
        elif n == 50:
            r = submit(client, version=version)
        elif n % 3 == 0:
            body: dict[str, Any] = {"version": version, "assistant": {"provider": "none"}}
            r = client.put("/api/airline/assistant", json=body)
        else:
            r = client.put("/api/airline/answers", json={"version": version, "answers": ANSWERS})
        codes.append(r.status_code)
        if r.status_code == 200:
            version = r.json()["version"]

    assert codes == [200] * 100 + [429]
    assert error_of(r) == "too_many_requests"
    assert "Retry-After" in r.headers
    [record] = docs(client, Collection.AIRLINES)
    actions = [e["action"] for e in record["history"]]
    assert len(actions) <= accounts.MAX_HISTORY
    assert actions[:3] == ["created", "answers_changed", "submitted"]
    assert actions[-1] == "assistant_changed"
    stored = AirlineRecord.model_validate(record)
    assert accounts.verify_history(stored.history) is None


def test_the_whole_site_s_saves_are_bounded_too(client: TestClient) -> None:
    """All airlines' saves together have a daily ceiling (3,000 on the server): new accounts
    cannot add up to the store's free writes."""
    client.app.state.airline_writes_all = server.LoginThrottle(  # type: ignore[attr-defined]
        max_failures=3, window_s=86400.0
    )
    first = signup(client).json()["airline"]["version"]
    assert client.put("/api/airline/draft", json=draft_body(first)).status_code == 200
    assert client.put("/api/airline/draft", json=draft_body(first + 1)).status_code == 200
    client.cookies.clear()
    other = signup(client, email="ops@rfb.example", headers=ip(2)).json()["airline"]["version"]
    assert client.put("/api/airline/draft", json=draft_body(other)).status_code == 200
    refused = client.put("/api/airline/draft", json=draft_body(other + 1))
    assert refused.status_code == 429
    assert error_of(refused) == "too_many_requests"


def test_signed_in_requests_are_throttled_before_the_store_is_read(client: TestClient) -> None:
    """Every signed-in request reads the login and the record: 60 in five minutes per address,
    and the 61st is refused before any read (batch 2 security finding 4)."""
    assert signup(client).status_code == 201
    reads: list[str] = []
    store = runtime_of(client).store
    real_get = store.get

    async def counted(collection: str, doc_id: str) -> dict[str, Any] | None:
        reads.append(str(collection))
        return await real_get(collection, doc_id)

    store.get = counted  # type: ignore[method-assign]
    codes = [client.get("/api/airline/me").status_code for _ in range(61)]
    assert codes == [200] * 60 + [429]
    assert len(reads) == 120
    assert client.get("/api/airline/me", headers=ip(9)).status_code == 200


def test_asking_whether_an_email_has_an_account_costs_a_sign_up(client: TestClient) -> None:
    """A 409 email_taken counts on the address's 3 sign-ups a day like an account made, so
    probing emails costs as much as making accounts (batch 2 security finding 3)."""
    assert signup(client).status_code == 201
    client.cookies.clear()
    taken = [signup(client, headers=ip(5)).status_code for _ in range(3)]
    assert taken == [409, 409, 409]
    refused = signup(client, email="ops@rfc.example", headers=ip(5))
    assert refused.status_code == 429
    assert signup(client, email="ops@rfc.example", headers=ip(6)).status_code == 201


def test_a_draft_not_saved_for_a_week_goes_with_its_login(client: TestClient) -> None:
    """Junk drafts cannot hold the 300-draft cap or an email for good (batch 2 security findings
    1 and 2): a draft not saved for DRAFT_DAYS goes at the next sign-up (at most hourly), login
    first, and its email can sign up again; a fresh draft and a submitted airline stay."""
    assert signup(client).status_code == 201
    client.cookies.clear()
    assert signup(client, email="ops@rfb.example", headers=ip(2)).status_code == 201
    client.cookies.clear()
    [old] = [d for d in docs(client, Collection.AIRLINES) if d["email"] == EMAIL]
    stale = AirlineRecord.model_validate(old)
    aged = stale.updated_at - timedelta(days=accounts.DRAFT_DAYS, minutes=1)
    put_docs(
        client,
        Collection.AIRLINES,
        {stale.id: {**old, "updated_at": aged.isoformat().replace("+00:00", "Z")}},
    )
    client.app.state.airline_purged_at = None  # type: ignore[attr-defined]
    assert signup(client, email="ops@rfc.example", headers=ip(3)).status_code == 201
    emails = sorted(d["email"] for d in docs(client, Collection.AIRLINES))
    assert emails == ["ops@rfb.example", "ops@rfc.example"]
    keys = {d["login_key"] for d in docs(client, Collection.AIRLINE_LOGINS)}
    assert accounts.login_key(EMAIL) not in keys
    client.cookies.clear()
    assert signup(client, headers=ip(4)).status_code == 201


async def test_a_purge_never_takes_a_newer_account_s_login(tmp_path: Path) -> None:
    """A record left by a failed sign-up has no login of its own: the email's login may be a newer
    account's, which the purge leaves alone."""
    from tephra.store import open_store

    store = open_store(make_settings(tmp_path))
    old_at = AT - timedelta(days=accounts.DRAFT_DAYS + 1)
    orphan = AirlineRecord(
        id="AL-000000000001",
        version=1,
        status="draft",
        login_key=accounts.login_key(EMAIL),
        email=EMAIL,
        draft=OnboardDraft(),
        created_at=old_at,
        updated_at=old_at,
        history=[accounts._entry([], at=old_at, actor="airline", action="created")],
    )
    await store.put(Collection.AIRLINES, orphan.id, orphan.model_dump(mode="json"))
    newer, login = await accounts.create_account(
        store, email=EMAIL, password_hash="x", recovery_sha256="0" * 64, at=AT
    )
    assert await accounts.purge_stale_drafts(store, now=AT) == 1
    assert await accounts.get_login(store, login.login_key) is not None
    assert (await accounts.get_record(store, newer.id)).status == "draft"


def test_a_name_holding_a_variable_is_refused() -> None:
    """The name may go into a .env file, whose loader expands ${VAR} in any quoting: a
    name holding one would print another setting (batch 2 security finding 6)."""
    bad = answers(airline__name="Air ${TEPHRA_SESSION_SECRET}")
    with pytest.raises(ValueError, match=r"must not contain \$\{"):
        AirlineAnswers.model_validate(bad)
    assert AirlineAnswers.model_validate(answers(airline__name="Air $ Co")).airline.name


def test_the_history_holds_at_most_its_cap() -> None:
    at = AT
    history = [accounts._entry([], at=at, actor="airline", action="created")]
    for n in range(accounts.MAX_HISTORY * 3):
        kind = "answers_changed" if n % 2 else "assistant_changed"
        history = accounts._with_own_change(history, at=at, action=kind)
    assert len(history) == accounts.MAX_HISTORY
    assert accounts.verify_history(history) is None
    same = accounts._with_own_change(history[:3], at=at, action=history[2].action)
    assert len(same) == 3


def test_a_desk_cookie_never_opens_a_workspace(client: TestClient) -> None:
    desk_login(client)
    assert client.get("/api/airline/me").status_code == 401
    assert client.get("/api/airline/session").json()["signed_in"] is False


# --- feature and secret gates -----------------------------------------------------------


def test_with_onboard_hidden_every_airline_route_is_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = airline_settings(tmp_path, features="connect")
    with use_clock(FixedClock(AT)), open_client(settings, monkeypatch)() as c:
        desk_login(c)
        answers_ = [request(c, method, path) for method, path in ACCOUNT_ROUTES + DESK_ROUTES]
        session = c.get("/api/airline/session")
        fleet = c.get("/api/fleet")

    assert [(r.status_code, error_of(r)) for r in answers_] == [(404, "feature_off")] * len(
        answers_
    )
    assert session.json() == {
        "accounts": False,
        "signed_in": False,
        "icao": None,
        "name": None,
        "status": None,
    }
    assert fleet.json() == {"own_fleet": None}


def test_a_blank_session_secret_turns_accounts_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blank = airline_settings(tmp_path).model_copy(update={"session_secret": SecretStr(" ")})
    with use_clock(FixedClock(AT)), open_client(blank, monkeypatch)() as c:
        refused = [request(c, method, path) for method, path in ACCOUNT_ROUTES]
        session = c.get("/api/airline/session")

    assert {(r.status_code, error_of(r)) for r in refused} == {(503, "accounts_off")}
    assert session.json()["accounts"] is False


# --- the Desk ---------------------------------------------------------------------------


def test_the_desk_needs_a_dispatcher(client: TestClient) -> None:
    signed_out = [request(client, method, path) for method, path in DESK_ROUTES]
    token, _ = sign_session(
        "Visitor-ab12",
        client.app.state.settings,  # type: ignore[attr-defined]
        at=wall_clock_now(),
        role="visitor",
        sid="0123456789abcdef",
    )
    client.cookies.set(DESK_COOKIE, token)
    visitor = [request(client, method, path) for method, path in DESK_ROUTES]

    assert {r.status_code for r in signed_out} == {401}
    assert {(r.status_code, error_of(r)) for r in visitor} == {(403, "visitor_role")}


def test_a_dispatcher_lists_verifies_and_declines(client: TestClient) -> None:
    first = onboard(client, headers=ip(70))
    gmail = answers(airline__aoc_number=None, airline__ops_email="ops@" + "gmail.com")
    second = onboard(client, email="desk@rfa-ops.example", body_answers=gmail, headers=ip(71))
    client.cookies.clear()
    desk_login(client)

    listed = client.get("/api/desk/airlines").json()["airlines"]
    summary = client.get("/api/desk/airlines/summary").json()
    view = client.get(f"/api/desk/airlines/{second['id']}").json()
    verify = client.post(
        f"/api/desk/airlines/{first['id']}/verify", json={"version": 2, "note": "AOC checked"}
    )
    again = client.post(f"/api/desk/airlines/{first['id']}/verify", json={"version": 3})
    stale = client.post(
        f"/api/desk/airlines/{second['id']}/decline", json={"version": 5, "reason": "Not real"}
    )
    decline = client.post(
        f"/api/desk/airlines/{second['id']}/decline", json={"version": 2, "reason": "Not real"}
    )
    missing = client.get("/api/desk/airlines/AL-ffffffffffff")
    malformed = client.get("/api/desk/airlines/not-an-id")
    declined = client.get("/api/desk/airlines?status=declined").json()["airlines"]
    everyone = client.get("/api/desk/airlines?status=all").json()["airlines"]

    assert {row["id"] for row in listed} == {second["id"], first["id"]}
    assert summary == {"pending": 2}
    assert view["email"] == "desk@rfa-ops.example"
    assert "contact email domain is a public mail provider" in view["flags"]
    assert "account email domain differs from the operations email's" in view["flags"]
    assert "no AOC number given" in view["flags"]
    assert view["history_ok"] is True
    assert view["aircraft"] == 3
    assert verify.status_code == 200
    assert verify.json()["status"] == "verified"
    history = verify.json()["history"]
    assert [e["action"] for e in history] == ["created", "submitted", "verified"]
    assert history[2]["actor"] == "desk:Ana K"
    assert history[2]["note"] == "AOC checked"
    assert history[2]["prev_sha256"] == history[1]["sha256"]
    assert (again.status_code, error_of(again)) == (422, "not_pending")
    assert (stale.status_code, error_of(stale)) == (409, "version_conflict")
    assert decline.json()["status"] == "declined"
    assert (missing.status_code, malformed.status_code) == (404, 404)
    assert [row["id"] for row in declined] == [second["id"]]
    assert len(everyone) == 2


def test_the_desk_never_sees_a_draft(client: TestClient) -> None:
    submitted = onboard(client, headers=ip(72))
    draft = signup(client, email="draft@rfa.example", headers=ip(73)).json()["airline"]
    client.cookies.clear()
    desk_login(client)

    lists = {
        status: [
            row["id"]
            for row in client.get(f"/api/desk/airlines?status={status}").json()["airlines"]
        ]
        for status in ("pending", "all")
    }
    asked = client.get("/api/desk/airlines?status=draft")
    one = client.get(f"/api/desk/airlines/{draft['id']}")
    verify = client.post(f"/api/desk/airlines/{draft['id']}/verify", json={"version": 1})
    decline = client.post(
        f"/api/desk/airlines/{draft['id']}/decline", json={"version": 1, "reason": "spam!"}
    )
    delete = client.post(f"/api/desk/airlines/{draft['id']}/delete", json={"version": 1})

    assert lists == {"pending": [submitted["id"]], "all": [submitted["id"]]}
    assert client.get("/api/desk/airlines/summary").json() == {"pending": 1}
    assert asked.status_code == 422
    assert [r.status_code for r in (one, verify, decline, delete)] == [404] * 4
    assert {d["id"] for d in docs(client, Collection.AIRLINES)} == {submitted["id"], draft["id"]}


def test_the_desk_deletes_only_a_declined_airline(client: TestClient) -> None:
    pending = onboard(client, headers=ip(80))
    other = onboard(client, email="b@rfa.example", headers=ip(81))
    client.cookies.clear()
    desk_login(client)
    refused = client.post(f"/api/desk/airlines/{pending['id']}/delete", json={"version": 2})
    client.post(f"/api/desk/airlines/{other['id']}/decline", json={"version": 2, "reason": "spam"})
    deleted = client.post(f"/api/desk/airlines/{other['id']}/delete", json={"version": 3})

    assert (refused.status_code, error_of(refused)) == (422, "not_declined")
    assert deleted.status_code == 204
    assert [d["id"] for d in docs(client, Collection.AIRLINES)] == [pending["id"]]
    assert [d["airline_id"] for d in docs(client, Collection.AIRLINE_LOGINS)] == [pending["id"]]


def test_a_broken_history_link_is_said(client: TestClient) -> None:
    view = onboard(client)
    [record] = docs(client, Collection.AIRLINES)
    record["history"][0]["note"] = "rewritten"
    put_docs(client, Collection.AIRLINES, {view["id"]: record})
    client.cookies.clear()
    desk_login(client)
    body = client.get(f"/api/desk/airlines/{view['id']}").json()
    assert (body["history_ok"], body["history_broken_at"]) == (False, 1)


# --- nothing reaches the shared picture -------------------------------------------------

WALL_CLOCK_KEYS = {"server_time", "last_tick_wall_at", "wall_at"}


def _frozen(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _frozen(v) for k, v in node.items() if k not in WALL_CLOCK_KEYS}
    if isinstance(node, list):
        return [_frozen(v) for v in node]
    return node


def picture(client: TestClient) -> dict[str, Any]:
    paths = [
        "/api/state",
        "/api/wall",
        "/api/audit?limit=200",
        "/api/advisories",
        "/api/connect/live",
    ]
    shown = {path: _frozen(client.get(path).json()) for path in paths}
    bus = runtime_of(client).bus
    shown["bus"] = {
        kind.value: [_frozen(e.data) for e in bus.recent(kind, limit=500)] for kind in SseEvent
    }
    return shown


def test_nothing_an_airline_or_the_desk_does_here_is_published(client: TestClient) -> None:
    desk_login(client)
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
        client.post(f"/api/desk/airlines/{first['id']}/verify", json={"version": 5}),
        client.post(
            f"/api/desk/airlines/{second['id']}/decline", json={"version": 2, "reason": "not real"}
        ),
        client.post(f"/api/desk/airlines/{second['id']}/delete", json={"version": 3}),
    ]
    assert signup(client, email="c@rfa.example", headers=ip(92)).status_code == 201
    steps.append(client.post("/api/airline/delete", json={"password": PASSWORD}, headers=ip(92)))
    after = picture(client)

    assert [r.status_code for r in steps] == [200] * 7 + [204, 204]
    assert [d["id"] for d in docs(client, Collection.AIRLINES)] == [first["id"]]
    assert json.dumps(after, sort_keys=True) == json.dumps(before, sort_keys=True)


def test_a_full_size_push_passes_the_dry_run_and_the_push(client: TestClient) -> None:
    """The dry run and the push share one body limit, and the kit's push.py batches fit it."""
    wall = datetime.now(UTC)

    def batch(at: datetime) -> dict[str, Any]:
        return {
            "format": "tephra.airline/1",
            "positions": [
                {
                    "hex": f"8a{n:04x}",
                    "callsign": f"RFA{n % 9000 + 100}",
                    "type_icao": "A320",
                    "lat": -5.26,
                    "lon": 105.79,
                    "alt_baro_ft": 14425,
                    "gs_kt": 393.0,
                    "track_deg": 89.6,
                    "observed_at": at.isoformat().replace("+00:00", "Z"),
                }
                for n in range(1000)
            ],
        }

    assert signup(client).status_code == 201
    dry = client.post("/api/airline/feeds/dry-run", json=batch(wall))
    assert dry.status_code == 200, dry.text
    assert dry.json()["positions"]["accepted"] == 1000
    client.cookies.clear()
    desk_login(client)
    key = client.post("/api/desk/connections", json={"name": "RFA ops"}).json()["key"]
    pushed = client.post(
        "/api/push/positions", json=batch(AT), headers={"Authorization": f"Bearer {key}"}
    )
    assert pushed.status_code == 200, pushed.status_code
    assert pushed.json()["accepted"] == 1000


def test_capacity_checks_count_and_read_no_record(client: TestClient) -> None:
    onboard(client)
    store = runtime_of(client).store
    read: list[str] = []
    real_query, real_list = store.query, store.list_docs

    async def query(collection: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        read.append(collection)
        return await real_query(collection, *args, **kwargs)

    async def list_docs(collection: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        read.append(collection)
        return await real_list(collection, *args, **kwargs)

    store.query, store.list_docs = query, list_docs  # type: ignore[method-assign]
    try:
        full = client.portal.call(accounts.onboarding_full, store)  # type: ignore[union-attr]
        pending = client.portal.call(accounts.pending_count, store)  # type: ignore[union-attr]
    finally:
        store.query, store.list_docs = real_query, real_list  # type: ignore[method-assign]
    assert (full, pending, read) == (False, 1, [])


async def test_the_desk_s_all_list_is_ordered_and_limited_by_the_store(tmp_path: Path) -> None:
    """ "All" asks the store for no filter, so Firestore orders and limits it (batch 2 security
    finding 5: a filter with an order runs in memory and reads every record); drafts, whose
    submitted_at is null and sorts last, are dropped here."""
    from tephra.store import open_store
    from tephra.store.firestore_store import plan_query

    store = open_store(make_settings(tmp_path))
    draft, _ = await accounts.create_account(
        store, email=EMAIL, password_hash="x", recovery_sha256="0" * 64, at=AT
    )
    sent, _ = await accounts.create_account(
        store, email="ops@rfb.example", password_hash="x", recovery_sha256="0" * 64, at=AT
    )
    model = AirlineAnswers.model_validate(ANSWERS)
    await accounts.submit(store, sent.id, version=sent.version, answers=model, flags=[], at=AT)
    calls: list[Any] = []
    real = store.query

    async def spy(collection: str, where: Any = (), **kw: Any) -> list[dict[str, Any]]:
        calls.append(list(where))
        return await real(collection, where, **kw)

    store.query = spy  # type: ignore[method-assign]
    listed = await accounts.list_airlines(store, "all", 50)
    assert [r.id for r in listed] == [sent.id]
    assert draft.id not in {r.id for r in listed}
    assert calls == [[]]
    plan = plan_query([], "submitted_at")
    assert plan.server_order
    assert plan.server_limit


def test_the_privacy_page_says_every_save_and_when_a_draft_goes() -> None:
    """Every time the answers are sent (a step's Next, Back, a step link, leaving the page) and the
    seven-day deletion of answers never submitted (batch 2 honesty finding 7, security 1)."""
    page = (Path(__file__).resolve().parents[1] / "tephra" / "web" / "privacy.html").read_text()
    assert "next or the previous page, open another step, or leave the page" in page
    assert accounts.DRAFT_DAYS == 7
    assert "deleted, with its answers, once seven days pass without a save" in page
    assert "Nothing expires it." not in page
