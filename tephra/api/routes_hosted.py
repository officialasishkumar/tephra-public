"""The root hosted routes, ``/api/hosted/...``: what a signed-in login may do about hosted
airlines (``me``), the record holder's set-up of their verified airline, and invite links
(look up, accept signed in, or join with a new account).

Never under ``/a/<ICAO>/`` (``tenancy.TENANT_ROUTES`` lists none of them). Every route binds the
wall clock, and anything that touches an airline's own documents goes through its space's
binding inside the hosted domain. Invite tokens travel only in JSON bodies, never in a path.
Errors never repeat what was typed (no email, no password).

``router`` is mounted under ``/api/hosted`` only with ``hosted`` on.
"""

from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from tephra.airline import accounts
from tephra.airline.models import AirlineLogin, AirlineRecord, AirlineSessionView
from tephra.airline.sessions import (
    AirlineContext,
    LoginContext,
    client_key_64,
    member_claims,
    read_claims,
    require_accounts,
    require_airline,
    require_login,
    set_airline_cookie,
)
from tephra.api import ApiError
from tephra.api.auth import require_csrf, wall_clock_now
from tephra.api.server import _json
from tephra.api.tenancy import bind_wall_clock, gate
from tephra.hosted import members, tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.models import (
    AcceptBody,
    HostedMe,
    InviteView,
    JoinBody,
    Membership,
    SetUpBody,
    TenantHeader,
    TokenBody,
)
from tephra.hosted.registry import TenantRegistry
from tephra.store.base import Store

__all__ = ["router"]

router = APIRouter(dependencies=[Depends(bind_wall_clock)])

SITE: Final = "site"
Csrf = [Depends(require_csrf)]
Login = Annotated[LoginContext, Depends(require_login)]
Holder = Annotated[AirlineContext, Depends(require_airline)]


class Joined(AirlineSessionView):
    """``POST /invites/join``: the new member-only login, signed in, and its recovery code,
    shown this once (as a new account's is): the only way back in without email."""

    recovery_code: str


def _registry(request: Request) -> TenantRegistry:
    registry: TenantRegistry = request.app.state.registry
    return registry


def _root(request: Request) -> Store:
    store: Store = request.app.state.runtime.store
    return store


def _access(request: Request) -> AccessCache:
    access: AccessCache = request.app.state.access
    return access


async def _record_of(request: Request, airline_id: str | None) -> AirlineRecord | None:
    if not airline_id:
        return None
    try:
        return await accounts.get_record(_root(request), airline_id)
    except accounts.AirlineNotFound:
        raise ApiError(401, "unauthenticated", "Sign in to your airline workspace") from None


def _invite_reads(request: Request) -> None:
    gate(
        request,
        "hosted_invite_reads",
        client_key_64(request),
        "too_many_requests",
        "Too many invite links tried from this address",
    )


def _gone() -> ApiError:
    return ApiError(404, "invite_gone", "This invite link is used, revoked or expired")


@router.get("/me", response_model=HostedMe)
async def get_me(request: Request, signed_in: Login) -> Response:
    """The login's airlines on TEPHRA, and what its own airline may do next."""
    record = await _record_of(request, signed_in.login.airline_id)
    most = request.app.state.settings.hosted_max_tenants
    return _json(
        await tenants.hosted_me(_root(request), signed_in.login, record, max_airlines=most)
    )


@router.post("/setup", response_model=TenantHeader, dependencies=Csrf)
async def set_up(body: SetUpBody, request: Request, airline: Holder) -> Response:
    """The record holder of a verified airline an operator approved for hosting creates its
    space (setup): they become its first ops manager, named ``display_name``."""
    record = airline.record
    if record.status != "verified" or record.answers is None:
        raise ApiError(409, "not_verified", "Your airline is not verified yet")
    icao = record.answers.airline.icao
    registry = _registry(request)
    _, member = await registry.set_up(record, airline.login, body.display_name)
    _access(request).drop(login_key=airline.login.login_key, icao=icao)
    handle = registry.handle(icao)
    if handle is None:
        raise ApiError(409, "not_verified", "Your airline could not be set up")
    return _json(await registry.header(handle, member))


@router.post("/invites/lookup", response_model=InviteView, dependencies=Csrf)
async def lookup(body: TokenBody, request: Request) -> Response:
    """What the join page shows before anyone signs in; every unusable link is the same 404."""
    _invite_reads(request)
    root = _root(request)
    login = await _signed_in_login(request)
    return _json(await members.invite_view(root, body.token, at=wall_clock_now(), login=login))


async def _signed_in_login(request: Request) -> AirlineLogin | None:
    """The browser's own sign-in, if any and still valid (the join page names it); never a
    401 here: the page is for people who are not signed in too."""
    claims = read_claims(request)
    if claims is None:
        return None
    login = await accounts.get_login(_root(request), claims.login_key)
    if login is None or login.session_version != claims.version:
        return None
    return login


@router.post("/invites/accept", response_model=Membership, dependencies=Csrf)
async def accept(body: AcceptBody, request: Request, signed_in: Login) -> Response:
    """A signed-in login takes the invite meant for its email (403 ``wrong_email``)."""
    _invite_reads(request)
    root = _root(request)
    found = await members.invite_by_token(root, body.token)
    if found is None:
        raise _gone()
    registry = _registry(request)
    held = registry.handle(found.icao)
    if held is None:
        raise _gone()
    member = await members.accept(
        root,
        body.token,
        signed_in.login,
        body.display_name,
        space=held.space,
        access=_access(request),
        at=wall_clock_now(),
    )
    handle = await registry.reload(found.icao)
    if handle is None:
        raise _gone()
    record = handle.record
    role = "ops_manager" if member.id in record.ops_managers else member.role
    return _json(Membership(icao=record.icao, name=record.name, role=role, state=record.state))


@router.post(
    "/invites/join",
    response_model=Joined,
    dependencies=[Depends(require_csrf), Depends(require_accounts)],
)
async def join(body: JoinBody, request: Request) -> Response:
    """A new account for the invited email, with no onboarding of its own, signed in.
    Throttled as a new account is; an email with an account is told to sign in first."""
    client = client_key_64(request)
    gate(
        request,
        "airline_signup_attempts",
        client,
        "too_many_requests",
        "Too many tries from this address",
    )
    for name, key in (("airline_signups", client), ("airline_signups_all", SITE)):
        throttle = getattr(request.app.state, name)
        if throttle.blocked(key):
            raise ApiError(
                429,
                "too_many_requests",
                "Too many new accounts from this address or on this server today",
                headers={"Retry-After": str(throttle.retry_after_s(key))},
            )
    root = _root(request)
    found = await members.invite_by_token(root, body.token)
    held = None if found is None else _registry(request).handle(found.icao)
    if found is None or held is None:
        raise _gone()
    login, _, code = await members.join(
        root,
        body.token,
        body.email,
        body.password,
        body.display_name,
        space=held.space,
        access=_access(request),
        at=wall_clock_now(),
    )
    for name, key in (("airline_signups", client), ("airline_signups_all", SITE)):
        getattr(request.app.state, name).record_failure(key)
    await _registry(request).reload(found.icao)
    response = _json(Joined(accounts=True, signed_in=True, recovery_code=code))
    set_airline_cookie(response, request, member_claims(login))
    return response
