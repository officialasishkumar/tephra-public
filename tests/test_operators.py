"""TEPHRA's operators (D9, S9, S10): the first from a one-time link that works only while no
operator is active, later ones invited by an operator and bound to an email, the cookie with
its own label, disable (never the last), sign-out everywhere, and the kill switch."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient

from tephra.airline import sessions
from tephra.hosted import operators
from tephra.hosted.models import HostedRefused, Operator
from tests.test_hosted_tenants import SECRET, site, wall, world

PASSWORD = "a long operator password"


async def first_operator(w: object, email: str = "m.tan@tephra.example") -> Operator:
    from tests.test_hosted_tenants import World

    assert isinstance(w, World)
    token = await operators.bootstrap_invite(w.root, "M. Tan", email, at=wall())
    return await operators.accept_invite(w.root, token, email, PASSWORD, access=w.access, at=wall())


async def test_the_bootstrap_link_works_only_while_no_operator_is_active(tmp_path: Path) -> None:
    w = world(tmp_path)
    spare = await operators.bootstrap_invite(w.root, "R. Osei", "r.osei@tephra.example", at=wall())
    tan = await first_operator(w)
    assert tan.session_version == 1
    assert tan.password.startswith("scrypt$")
    with pytest.raises(HostedRefused) as refused:
        await operators.bootstrap_invite(w.root, "Eve", "eve@tephra.example", at=wall())
    assert (refused.value.status, refused.value.code) == (409, "operators_exist")
    with pytest.raises(HostedRefused, match="invite_gone"):
        await operators.accept_invite(
            w.root, spare, "r.osei@tephra.example", PASSWORD, access=w.access, at=wall()
        )
    await w.aclose()


async def test_an_invite_is_bound_to_its_email_and_used_once(tmp_path: Path) -> None:
    w = world(tmp_path)
    tan = await first_operator(w)
    token = await operators.invite(w.root, "R. Osei", "r.osei@tephra.example", by=tan, at=wall())
    view = await operators.invite_view(w.root, token, at=wall())
    assert (view.name, view.email_hint) == ("R. Osei", "r•••@tephra.example")
    with pytest.raises(HostedRefused, match="wrong_email"):
        await operators.accept_invite(
            w.root, token, "eve@tephra.example", PASSWORD, access=w.access, at=wall()
        )
    osei = await operators.accept_invite(
        w.root, token, "R.Osei@tephra.example", PASSWORD, access=w.access, at=wall()
    )
    assert osei.email == "r.osei@tephra.example"
    with pytest.raises(HostedRefused, match="invite_gone"):
        await operators.accept_invite(
            w.root, token, "r.osei@tephra.example", PASSWORD, access=w.access, at=wall()
        )
    with pytest.raises(HostedRefused, match="email_taken"):
        await operators.invite(w.root, "Again", "r.osei@tephra.example", by=tan, at=wall())
    late = await operators.invite(w.root, "J. Park", "j.park@tephra.example", by=tan, at=wall())
    with pytest.raises(HostedRefused, match="invite_gone"):
        await operators.invite_view(w.root, late, at=wall() + timedelta(hours=25))
    await w.aclose()


async def test_sign_in_checks_the_password_and_disabled_operators(tmp_path: Path) -> None:
    w = world(tmp_path)
    tan = await first_operator(w)
    found = await operators.check_sign_in(w.root, "M.TAN@tephra.example", PASSWORD)
    assert found is not None
    assert found.login_key == tan.login_key
    assert await operators.check_sign_in(w.root, tan.email, "wrong password!") is None
    assert await operators.check_sign_in(w.root, "nobody@tephra.example", PASSWORD) is None
    await w.aclose()


async def test_disable_never_takes_the_last_and_ends_sessions(tmp_path: Path) -> None:
    w = world(tmp_path)
    tan = await first_operator(w)
    with pytest.raises(HostedRefused, match="last_operator"):
        await operators.disable(w.root, tan.login_key, by=tan, access=w.access, at=wall())
    token = await operators.invite(w.root, "R. Osei", "r.osei@tephra.example", by=tan, at=wall())
    osei = await operators.accept_invite(
        w.root, token, "r.osei@tephra.example", PASSWORD, access=w.access, at=wall()
    )
    assert await w.access.operator(w.root, osei.login_key, 1) is not None
    listed = await operators.disable(w.root, osei.login_key, by=tan, access=w.access, at=wall())
    gone = next(op for op in listed if op.login_key == osei.login_key)
    assert gone.disabled is not None
    assert gone.disabled.by == operators.operator_by(tan)
    assert await w.access.operator(w.root, osei.login_key, 1) is None
    assert await operators.check_sign_in(w.root, osei.email, PASSWORD) is None
    await w.aclose()


async def test_sign_out_bumps_the_version_on_the_next_request(tmp_path: Path) -> None:
    w = world(tmp_path)
    tan = await first_operator(w)
    assert await w.access.operator(w.root, tan.login_key, 1) is not None
    await operators.sign_out(w.root, tan.login_key, access=w.access)
    assert await w.access.operator(w.root, tan.login_key, 1) is None
    assert await w.access.operator(w.root, tan.login_key, 2) is not None
    await w.aclose()


async def test_the_task_tokens_revoke_is_a_kill_switch(tmp_path: Path) -> None:
    w = world(tmp_path)
    tan = await first_operator(w)
    revoked = await operators.revoke(w.root, tan.email, access=w.access, at=wall())
    assert revoked.disabled is not None
    with pytest.raises(HostedRefused, match="not_found"):
        await operators.revoke(w.root, "nobody@tephra.example", access=w.access, at=wall())
    again = await first_operator(w, "j.park@tephra.example")
    assert again.disabled is None
    await w.aclose()


def test_the_short_key_and_the_stamp() -> None:
    op = Operator(
        login_key="4f1c2a9be07d" + "0" * 52,
        email="m.tan@tephra.example",
        name="M. Tan",
        password="scrypt$x",
        created_at=wall(),
    )
    assert operators.short_key(op) == "4f1c2a9be07d"
    assert operators.operator_by(op) == "operator:M. Tan#4f1c2a9b"
    view = operators.operator_view(op, you=op)
    assert view.you is True
    assert "password" not in view.model_dump()


def cookie_app(tmp_path: Path) -> tuple[TestClient, Operator]:
    settings = site(tmp_path)
    op = Operator(
        login_key="ab" * 32,
        email="m.tan@tephra.example",
        name="M. Tan",
        password="scrypt$x",
        session_version=3,
        created_at=wall(),
    )
    app = FastAPI()

    @app.post("/in")
    def sign_in() -> Response:
        response = Response(status_code=204)
        operators.issue_operator_cookie(response, op, settings, secure=False)
        return response

    @app.get("/who")
    def who(request: Request) -> dict[str, object]:
        claims = operators.read_operator_claims(request, settings)
        airline = sessions.verify_claims(
            request.cookies.get(operators.COOKIE_NAME, ""), settings, at=wall()
        )
        return {
            "k": None if claims is None else claims.login_key,
            "v": None if claims is None else claims.version,
            "as_airline": airline is not None,
        }

    return TestClient(app), op


def test_the_cookie_round_trips_and_is_not_an_airline_cookie(tmp_path: Path) -> None:
    client, op = cookie_app(tmp_path)
    response = client.post("/in")
    header = response.headers["set-cookie"]
    assert "HttpOnly" in header
    assert "SameSite=strict" in header
    assert "Max-Age=28800" in header
    assert client.get("/who").json() == {"k": op.login_key, "v": 3, "as_airline": False}
    value = client.cookies[operators.COOKIE_NAME]
    client.cookies.set(
        operators.COOKIE_NAME, value[:-2] + ("A" if value[-2] != "A" else "B") + value[-1]
    )
    assert client.get("/who").json()["k"] is None


def test_a_cookie_signed_with_another_secret_is_refused(tmp_path: Path) -> None:
    client, _ = cookie_app(tmp_path)
    client.post("/in")
    other = site(tmp_path, session_secret="z" * 40)
    assert other.session_secret.get_secret_value() != SECRET

    request = Request(
        {
            "type": "http",
            "headers": [
                (
                    b"cookie",
                    f"{operators.COOKIE_NAME}={client.cookies[operators.COOKIE_NAME]}".encode(),
                )
            ],
        }
    )
    assert operators.read_operator_claims(request, other) is None
