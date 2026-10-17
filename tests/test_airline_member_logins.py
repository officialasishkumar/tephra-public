"""Airline accounts under hosting (SPEC §3.3-3.4): member-only logins (an empty ``a`` in the
cookie), ``require_login`` beside ``require_airline``, sign-out everywhere, the last sign-in,
an operator's hosting approval, and the deletion guards. With hosting off nothing a stored
document or an answer carries changes."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tephra.airline import accounts, sessions
from tephra.airline.models import AirlineLogin, Stamp
from tephra.api import ApiError
from tephra.api.auth import LoginThrottle
from tephra.hosted import members, tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.throttles import HOSTED_THROTTLES
from tests.test_hosted_tenants import OPERATOR, World, airline_account, set_up, site, wall, world


def app_for(w: World) -> TestClient:
    app = FastAPI()
    app.state.settings = w.settings
    app.state.runtime = SimpleNamespace(store=w.root)
    for name, (tries, window) in (sessions.THROTTLES | HOSTED_THROTTLES).items():
        setattr(app.state, name, LoginThrottle(max_failures=tries, window_s=window))

    @app.exception_handler(ApiError)
    async def refused(_request: object, exc: ApiError) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse({"code": exc.error}, status_code=exc.status_code)

    @app.get("/login")
    async def login(
        ctx: sessions.LoginContext = Depends(sessions.require_login),
    ) -> dict[str, object]:
        return {"key": ctx.login.login_key, "airline": ctx.login.airline_id}

    @app.get("/airline")
    async def airline(
        ctx: sessions.AirlineContext = Depends(sessions.require_airline),
    ) -> dict[str, str]:
        return {"id": ctx.record.id}

    return TestClient(app)


def sign(w: World, claims: sessions.AirlineClaims) -> str:
    token, _ = sessions.sign_claims(claims, w.settings, at=wall())
    return token


def test_a_cookie_with_an_empty_airline_id_verifies(tmp_path: Path) -> None:
    settings = site(tmp_path)
    login = AirlineLogin(
        login_key="a" * 64,
        airline_id=None,
        email="vic@rfb.example",
        password="scrypt$x",
        recovery_sha256="0" * 64,
        session_version=2,
        created_at=wall(),
        password_changed_at=wall(),
    )
    claims = sessions.member_claims(login)
    token, _ = sessions.sign_claims(claims, settings, at=wall())
    back = sessions.verify_claims(token, settings, at=wall())
    assert back is not None
    assert (back.airline_id, back.login_key, back.version, back.icao) == ("", "a" * 64, 2, "")


async def test_require_login_and_require_airline_for_both_kinds_of_login(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, record, holder = await set_up(w)
    _, token = await members.invite(
        w.root, "RFB", "vic@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    vic, _, _ = await members.join(
        w.root,
        token,
        "vic@rfb.example",
        "a long password 1",
        "Vic View",
        space=w.space("RFB"),
        access=w.access,
        at=wall(),
    )
    client = app_for(w)
    client.cookies.set(sessions.COOKIE_NAME, sign(w, sessions.claims_of(record, holder)))
    assert client.get("/airline").json() == {"id": record.id}
    assert client.get("/login").json() == {"key": holder.login_key, "airline": record.id}
    client.cookies.set(sessions.COOKIE_NAME, sign(w, sessions.member_claims(vic)))
    assert client.get("/login").json() == {"key": vic.login_key, "airline": None}
    refused = client.get("/airline")
    assert (refused.status_code, refused.json()) == (404, {"code": "no_airline_record"})
    forged = sessions.AirlineClaims("", holder.login_key, holder.session_version, "", "")
    client.cookies.set(sessions.COOKIE_NAME, sign(w, forged))
    assert client.get("/login").status_code == 401
    assert client.get("/airline").status_code == 401
    await w.aclose()


async def test_sign_out_everywhere_ends_every_cookie_of_the_login(tmp_path: Path) -> None:
    w = world(tmp_path)
    record, login = await airline_account(w.root)
    client = app_for(w)
    client.cookies.set(sessions.COOKIE_NAME, sign(w, sessions.claims_of(record, login)))
    assert client.get("/airline").status_code == 200
    cache = AccessCache()
    await sessions.sign_out_everywhere(w.root, login.login_key, access=cache)
    assert client.get("/airline").status_code == 401
    stored = await accounts.get_login(w.root, login.login_key)
    assert stored is not None
    assert stored.session_version == login.session_version + 1
    await w.aclose()


async def test_the_last_sign_in_is_kept_and_left_out_until_set(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, login = await airline_account(w.root)
    assert "last_sign_in_at" not in login.model_dump(mode="json")
    at = wall()
    await accounts.note_sign_in(w.root, login.login_key, at=at)
    stored = await accounts.get_login(w.root, login.login_key)
    assert stored is not None
    assert stored.last_sign_in_at is not None
    assert abs((stored.last_sign_in_at - at).total_seconds()) < 0.01
    await w.aclose()


async def test_hosting_is_left_out_of_a_record_until_an_operator_approves(tmp_path: Path) -> None:
    w = world(tmp_path)
    record, _ = await airline_account(w.root, hosting=False)
    assert record.hosting is None
    assert "hosting" not in record.model_dump(mode="json")
    approved = await accounts.approve_hosting(
        w.root, record.id, by=OPERATOR, version=record.version, at=wall()
    )
    assert approved.hosting is not None
    assert approved.hosting.by == OPERATOR
    assert approved.history[-1].action == "hosting_approved"
    again = await accounts.approve_hosting(
        w.root, approved.id, by="operator:R. Osei#9a0b7c6d", version=approved.version, at=wall()
    )
    assert again.hosting == approved.hosting
    pending, _ = await airline_account(w.root, "RFC", verified=False)
    with pytest.raises(accounts.NotVerified):
        await accounts.approve_hosting(
            w.root, pending.id, by=OPERATOR, version=pending.version, at=wall()
        )
    with pytest.raises(ValueError, match="only a verify"):
        await accounts.decide(
            w.root,
            pending.id,
            version=pending.version,
            actor=OPERATOR,
            verified=False,
            note="No.",
            at=wall(),
            hosting=Stamp(by=OPERATOR, at=wall()),
        )
    await w.aclose()


async def test_the_desk_verify_never_approves_hosting(tmp_path: Path) -> None:
    w = world(tmp_path)
    record, _ = await airline_account(w.root, hosting=False)
    assert record.status == "verified"
    assert record.hosting is None
    await w.aclose()


async def test_deletion_is_refused_for_a_hosted_airline_and_a_last_ops_manager(
    tmp_path: Path,
) -> None:
    w = world(tmp_path)
    _, ana, record, holder = await set_up(w)
    assert await accounts.deletion_refusal(w.root, holder, record) == "hosted_airline"
    _, token = await members.invite(
        w.root, "RFB", "vic@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    vic, _, _ = await members.join(
        w.root,
        token,
        "vic@rfb.example",
        "a long password 1",
        "Vic View",
        space=w.space("RFB"),
        access=w.access,
        at=wall(),
    )
    assert await accounts.deletion_refusal(w.root, vic, None) is None
    await members.set_role(
        w.root,
        "RFB",
        tenants.member_id("RFB", vic.login_key),
        "ops_manager",
        by=ana,
        space=w.space("RFB"),
        access=w.access,
        at=wall(),
    )
    await members.leave(w.root, "RFB", ana.id, space=w.space("RFB"), access=w.access, at=wall())
    assert await accounts.deletion_refusal(w.root, vic, None) == "last_ops_manager"
    other, other_login = await airline_account(w.root, "RFC")
    assert await accounts.deletion_refusal(w.root, other_login, other) is None
    await w.aclose()
