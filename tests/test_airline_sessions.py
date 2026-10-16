"""The airline workspace cookie: signed apart from the Desk's, wall-clock expiry, no store read
for the nav, and a recovery's new session version signing other browsers out."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr
from test_airline_api import (
    AT,
    airline_settings,
    docs,
    open_client,
    put_docs,
    runtime_of,
    signup,
)

from tephra.airline.sessions import (
    COOKIE_NAME,
    AirlineClaims,
    read_claims,
    sign_claims,
    verify_claims,
)
from tephra.api.auth import sign_session, verify_session
from tephra.config import Settings
from tephra.store.base import Collection
from tephra.util.timeutil import FixedClock, use_clock

SECRET = "test-session-secret-0123456789abcdef"
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
CLAIMS = AirlineClaims("AL-0123456789ab", "a" * 64, 1, "RFA", "Ring of Fire Air")


def settings(**changes: Any) -> Settings:
    return Settings(_env_file=None, **{"session_secret": SecretStr(SECRET), **changes})


def test_a_cookie_round_trips_and_carries_its_claims() -> None:
    token, expires = sign_claims(CLAIMS, settings(), at=NOW)
    claims = verify_claims(token, settings(), at=NOW)

    assert expires == NOW + timedelta(hours=12)
    assert claims == replace(CLAIMS, expires_at=expires)


def test_desk_and_airline_cookies_never_verify_as_each_other() -> None:
    airline, _ = sign_claims(CLAIMS, settings(), at=NOW)
    desk, _ = sign_session("Ana K", settings(), at=NOW)

    assert verify_session(airline, settings(), at=NOW) is None
    assert verify_claims(desk, settings(), at=NOW) is None


def test_a_drafts_cookie_has_no_icao_or_name_but_still_needs_its_ids() -> None:
    """A draft has no checked ICAO or name until it submits: the cookie carries both empty."""
    draft = replace(CLAIMS, icao="", name="")
    token, expires = sign_claims(draft, settings(), at=NOW)
    no_id, _ = sign_claims(replace(CLAIMS, airline_id=""), settings(), at=NOW)
    no_key, _ = sign_claims(replace(CLAIMS, login_key=""), settings(), at=NOW)

    assert verify_claims(token, settings(), at=NOW) == replace(draft, expires_at=expires)
    assert verify_claims(no_id, settings(), at=NOW) is None
    assert verify_claims(no_key, settings(), at=NOW) is None


def test_a_tampered_or_foreign_cookie_fails() -> None:
    token, _ = sign_claims(CLAIMS, settings(), at=NOW)
    payload, _, mac = token.partition(".")
    other, _ = sign_claims(CLAIMS, settings(session_secret=SecretStr("x" * 40)), at=NOW)

    assert verify_claims(payload[:-2] + "AA." + mac, settings(), at=NOW) is None
    assert verify_claims(other, settings(), at=NOW) is None
    assert verify_claims("not-a-cookie", settings(), at=NOW) is None


def test_expiry_is_on_the_wall_clock_not_the_replay_clock() -> None:
    token, expires = sign_claims(CLAIMS, settings(airline_session_ttl_h=1), at=NOW)

    assert verify_claims(token, settings(), at=expires - timedelta(seconds=1)) is not None
    assert verify_claims(token, settings(), at=expires) is None
    with use_clock(FixedClock(NOW - timedelta(days=40))):  # a replay clock in the past
        fresh, _ = sign_claims(CLAIMS, settings(), at=datetime.now(UTC))
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(settings=settings())),
            cookies={COOKIE_NAME: fresh},
        )
        assert read_claims(request) is not None  # type: ignore[arg-type]
        request.cookies = {COOKIE_NAME: token}  # expired on the wall clock long ago
        assert read_claims(request) is None  # type: ignore[arg-type]


def test_reading_the_claims_needs_no_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("the nav must not read the store")

    with use_clock(FixedClock(AT)), open_client(airline_settings(tmp_path), monkeypatch)() as c:
        assert signup(c).status_code == 201
        store = runtime_of(c).store
        for name in ("get", "query", "list_docs", "update", "put"):
            monkeypatch.setattr(store, name, refuse)
        session = c.get("/api/airline/session")

    assert session.json()["signed_in"] is True


def test_a_new_session_version_signs_other_browsers_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with use_clock(FixedClock(AT)), open_client(airline_settings(tmp_path), monkeypatch)() as c:
        assert signup(c).status_code == 201
        assert c.get("/api/airline/me").status_code == 200
        [login] = docs(c, Collection.AIRLINE_LOGINS)
        put_docs(
            c, Collection.AIRLINE_LOGINS, {login["login_key"]: {**login, "session_version": 2}}
        )
        after = c.get("/api/airline/me")
        signed_in = c.get("/api/airline/session").json()["signed_in"]

    assert after.status_code == 401
    assert signed_in is True  # the nav reads the cookie alone; every action checks the store


def test_a_cookie_means_nothing_where_onboarding_is_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings_on = airline_settings(tmp_path)
    with use_clock(FixedClock(AT)), open_client(settings_on, monkeypatch)() as c:
        assert signup(c).status_code == 201
        cookie = c.cookies[COOKIE_NAME]
    off = airline_settings(tmp_path, features="connect")
    with use_clock(FixedClock(AT)), open_client(off, monkeypatch)() as c:
        c.cookies.set(COOKIE_NAME, cookie)
        assert c.get("/api/airline/session").json()["signed_in"] is False
