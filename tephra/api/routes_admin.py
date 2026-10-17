"""The operators' console API (``/api/admin``) and the operator tasks (``/tasks/operator-*``).

Operators are TEPHRA's own people (D9): never an airline member and never a Desk role. Their
cookie ``tephra_operator`` is checked against the operator document on every request through
the access cache, which every operator function empties for the operator it changes. The first
operator comes from a one-time link the task token mints, only while no operator is active;
every later one is invited from the console. Every route binds the wall clock, and every action
on an airline is recorded in that airline's own chain by the hosted domain.

``router`` is mounted under ``/api/admin`` and ``tasks`` at the root, only with ``hosted`` on.
"""

import re
from datetime import datetime
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import TypeAdapter

from tephra.airline import accounts
from tephra.airline.models import Stamp
from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.airline.sessions import client_key_64
from tephra.api import ApiError
from tephra.api.auth import (
    COOKIE_NAME as DESK_COOKIE,
)
from tephra.api.auth import (
    is_https,
    require_csrf,
    require_task_token,
    wall_clock_now,
)
from tephra.api.server import _json
from tephra.api.tenancy import bind_wall_clock, gate
from tephra.hosted import members, operators, tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.models import (
    AdminContact,
    AdminList,
    AdminRow,
    ConfirmIcaoBody,
    DeclineBody,
    EmailBody,
    Operator,
    OperatorAcceptBody,
    OperatorInviteBody,
    OperatorInviteView,
    OperatorSignIn,
    OperatorView,
    ReasonBody,
    TokenBody,
    VerifyBody,
    VersionBody,
)
from tephra.hosted.registry import TenantHandle, TenantRegistry
from tephra.models import TephraModel, UtcDatetime
from tephra.store.base import Store

__all__ = ["router", "tasks"]

router = APIRouter(dependencies=[Depends(bind_wall_clock)])
tasks = APIRouter(dependencies=[Depends(bind_wall_clock)])

TRIES_HEADER: Final = "X-Tephra-Tries-Left"
SITE: Final = "site"
Csrf = [Depends(require_csrf)]


class OperatorLink(TephraModel):
    """A one-time operator link; the token travels only in its fragment, shown once."""

    link: str
    expires_at: UtcDatetime


_OPERATORS: Final = TypeAdapter(list[OperatorView])


# --- helpers ----------------------------------------------------------------------------


def _root(request: Request) -> Store:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    store: Store = runtime.store
    return store


def _access(request: Request) -> AccessCache:
    access: AccessCache = request.app.state.access
    return access


def _origin(request: Request) -> str:
    """``https://<host>`` behind Cloud Run's front end, the request's own scheme locally."""
    scheme = "https" if is_https(request) else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}"


def _link(request: Request, token: str, expires_at: datetime) -> OperatorLink:
    return OperatorLink(link=f"{_origin(request)}/admin/join#{token}", expires_at=expires_at)


def _view(op: Operator, *, you: Operator | None) -> Response:
    return _json(operators.operator_view(op, you=you))


async def require_operator(request: Request) -> Operator:
    """The signed-in operator, checked against the stored operator (through the access cache):
    401 signed out; 403 ``operator_only`` for someone signed in as an airline or at the Desk."""
    claims = operators.read_operator_claims(request, request.app.state.settings)
    if claims is None:
        if request.cookies.get(AIRLINE_COOKIE) or request.cookies.get(DESK_COOKIE):
            raise ApiError(403, "operator_only", "TEPHRA's operators only")
        raise ApiError(401, "unauthenticated", "Sign in as an operator")
    op = await _access(request).operator(_root(request), claims.login_key, claims.version)
    if op is None:
        raise ApiError(401, "unauthenticated", "Sign in as an operator")
    return op


OperatorDep = Annotated[Operator, Depends(require_operator)]


# --- the operator tasks (task token) ----------------------------------------------------


@tasks.post(
    "/tasks/operator-invite",
    response_model=OperatorLink,
    dependencies=[Depends(require_task_token)],
)
async def operator_bootstrap(body: OperatorInviteBody, request: Request) -> Response:
    """The first operator's one-time link; 409 ``operators_exist`` once any is active (S10)."""
    at = wall_clock_now()
    token = await operators.bootstrap_invite(_root(request), body.name, body.email, at=at)
    return _json(_link(request, token, at + operators.INVITE_LIFE))


@tasks.post("/tasks/operator-revoke", status_code=204, dependencies=[Depends(require_task_token)])
async def operator_revoke(body: EmailBody, request: Request) -> Response:
    """The kill switch: the operator is disabled and every session of theirs ends."""
    await operators.revoke(_root(request), body.email, access=_access(request), at=wall_clock_now())
    return Response(status_code=204)


# --- signing in -------------------------------------------------------------------------


@router.post("/invite/lookup", response_model=OperatorInviteView, dependencies=Csrf)
async def invite_lookup(body: TokenBody, request: Request) -> Response:
    gate(
        request,
        "hosted_invite_reads",
        client_key_64(request),
        "too_many_requests",
        "Too many invite lookups from this address",
    )
    view = await operators.invite_view(_root(request), body.token, at=wall_clock_now())
    return _json(view)


@router.post("/invite/accept", response_model=OperatorView, dependencies=Csrf)
async def invite_accept(body: OperatorAcceptBody, request: Request) -> Response:
    gate(
        request,
        "hosted_invite_reads",
        client_key_64(request),
        "too_many_requests",
        "Too many invite lookups from this address",
    )
    op = await operators.accept_invite(
        _root(request),
        body.token,
        body.email,
        body.password,
        access=_access(request),
        at=wall_clock_now(),
    )
    response = _view(op, you=op)
    operators.issue_operator_cookie(
        response, op, request.app.state.settings, secure=is_https(request)
    )
    return response


@router.post("/sign-in", response_model=OperatorView, dependencies=Csrf)
async def sign_in(body: OperatorSignIn, request: Request) -> Response:
    """Five tries per address and ten per email in 15 minutes; a wrong try says how many are
    left (``X-Tephra-Tries-Left``), and an unknown email costs the same as a wrong password."""
    client, email_key = client_key_64(request), operators.login_key(body.email)
    by_client = request.app.state.operator_login
    by_email = request.app.state.operator_login_email
    waits = [
        throttle.retry_after_s(key)
        for throttle, key in ((by_client, client), (by_email, email_key))
        if throttle.blocked(key)
    ]
    if waits:
        raise ApiError(
            429,
            "too_many_attempts",
            "Too many tries; sign-in waits",
            headers={"Retry-After": str(max(waits))},
        )
    root = _root(request)
    op = await operators.check_sign_in(root, body.email, body.password)
    if op is None:
        by_client.record_failure(client)
        by_email.record_failure(email_key)
        left = min(by_client.remaining(client), by_email.remaining(email_key))
        raise ApiError(
            401,
            "bad_credentials",
            "That email and password don't match",
            headers={TRIES_HEADER: str(left)},
        )
    by_email.clear(email_key)
    op = await operators.note_sign_in(root, op, at=wall_clock_now())
    response = _view(op, you=op)
    operators.issue_operator_cookie(
        response, op, request.app.state.settings, secure=is_https(request)
    )
    return response


@router.post("/sign-out", status_code=204, dependencies=Csrf)
async def sign_out(request: Request) -> Response:
    """Every browser of this operator is signed out (a new session version)."""
    claims = operators.read_operator_claims(request, request.app.state.settings)
    if claims is not None:
        await operators.sign_out(_root(request), claims.login_key, access=_access(request))
    response = Response(status_code=204)
    operators.clear_operator_cookie(response, secure=is_https(request))
    return response


@router.get("/me", response_model=OperatorView)
async def me(request: Request) -> Response:
    """The signed-in operator, or 401 for anyone else, an airline or Desk sign-in included
    (SPEC §4.2: the account menu asks it on every page and shows Admin on a 200 only)."""
    claims = operators.read_operator_claims(request, request.app.state.settings)
    op = (
        None
        if claims is None
        else await _access(request).operator(_root(request), claims.login_key, claims.version)
    )
    if op is None:
        raise ApiError(401, "unauthenticated", "Sign in as an operator")
    return _view(op, you=op)


# --- operators --------------------------------------------------------------------------


def _operators(found: list[Operator], you: Operator) -> Response:
    views = [operators.operator_view(o, you=you) for o in found]
    return Response(_OPERATORS.dump_json(views), media_type="application/json")


@router.get("/operators", response_model=list[OperatorView])
async def list_operators(op: OperatorDep, request: Request) -> Response:
    return _operators(await operators.list_operators(_root(request)), op)


@router.post("/operators/invites", response_model=OperatorLink, dependencies=Csrf)
async def invite_operator(body: OperatorInviteBody, op: OperatorDep, request: Request) -> Response:
    gate(request, "operator_invites", SITE, "too_many_requests", "Five operator invites a day")
    at = wall_clock_now()
    token = await operators.invite(_root(request), body.name, body.email, by=op, at=at)
    return _json(_link(request, token, at + operators.INVITE_LIFE))


@router.post("/operators/{k}/disable", response_model=list[OperatorView], dependencies=Csrf)
async def disable_operator(k: str, op: OperatorDep, request: Request) -> Response:
    root = _root(request)
    target = await operators.find_by_k(root, k)
    if target is None:
        raise ApiError(404, "not_found", "No such operator")
    found = await operators.disable(
        root, target.login_key, by=op, access=_access(request), at=wall_clock_now()
    )
    return _operators(found, op)


# --- airlines ---------------------------------------------------------------------------

_AIRLINE_ID: Final = re.compile(r"AL-[0-9a-f]{12}")
_ICAO: Final = re.compile(r"[A-Z]{3}")


def _registry(request: Request) -> TenantRegistry:
    registry: TenantRegistry = request.app.state.registry
    return registry


async def _row(request: Request, airline_id: str) -> Response:
    """The console row of one airline after an action (from the same builder as the list)."""
    listed = await _registry(request).admin_list()
    for row in listed.rows:
        if row.airline_id == airline_id:
            return _json(row)
    raise ApiError(404, "not_found", "No such airline")


def _airline_id(airline_id: str) -> str:
    if _AIRLINE_ID.fullmatch(airline_id) is None:
        raise ApiError(404, "not_found", "No such airline")
    return airline_id


def _handle(request: Request, icao: str) -> TenantHandle:
    handle = _registry(request).handle(icao) if _ICAO.fullmatch(icao) else None
    if handle is None:
        raise ApiError(404, "not_found", "No such airline")
    return handle


def _version_conflict() -> ApiError:
    return ApiError(409, "version_conflict", "This airline changed since you loaded it")


@router.get("/airlines", response_model=AdminList)
async def list_airlines(op: OperatorDep, request: Request) -> Response:
    """Places, the free-tier meter, memory, the last pass and every submitted airline's row;
    airlines still onboarding are a count only."""
    return _json(await _registry(request).admin_list())


async def _decide(
    request: Request,
    op: Operator,
    airline_id: str,
    *,
    verified: bool,
    version: int,
    note: str | None,
) -> Response:
    at = wall_clock_now()
    by = operators.operator_by(op)
    try:
        await accounts.decide(
            _root(request),
            _airline_id(airline_id),
            version=version,
            actor=by,
            verified=verified,
            note=note,
            at=at,
            hosting=Stamp(by=by, at=at) if verified else None,
        )
    except accounts.AirlineNotFound:
        raise ApiError(404, "not_found", "No such airline") from None
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.NotPending:
        raise ApiError(409, "not_pending", "Only an airline pending verification") from None
    return await _row(request, airline_id)


@router.post("/airlines/{airline_id}/verify", response_model=AdminRow, dependencies=Csrf)
async def verify(airline_id: str, body: VerifyBody, op: OperatorDep, request: Request) -> Response:
    """A person checked who this operator is; an operator's verify also approves hosting."""
    return await _decide(
        request, op, airline_id, verified=True, version=body.version, note=body.note
    )


@router.post("/airlines/{airline_id}/decline", response_model=AdminRow, dependencies=Csrf)
async def decline(
    airline_id: str, body: DeclineBody, op: OperatorDep, request: Request
) -> Response:
    return await _decide(
        request, op, airline_id, verified=False, version=body.version, note=body.reason
    )


@router.post("/airlines/{airline_id}/approve-hosting", response_model=AdminRow, dependencies=Csrf)
async def approve_hosting(
    airline_id: str, body: VersionBody, op: OperatorDep, request: Request
) -> Response:
    """Hosting for an airline the Desk verified (D24): the Desk's verify never sets it."""
    try:
        await accounts.approve_hosting(
            _root(request),
            _airline_id(airline_id),
            by=operators.operator_by(op),
            version=body.version,
            at=wall_clock_now(),
        )
    except accounts.AirlineNotFound:
        raise ApiError(404, "not_found", "No such airline") from None
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.NotVerified:
        raise ApiError(409, "not_verified", "Only a verified airline") from None
    return await _row(request, airline_id)


@router.post("/tenants/{icao}/suspend", response_model=AdminRow, dependencies=Csrf)
async def suspend(icao: str, body: ReasonBody, op: OperatorDep, request: Request) -> Response:
    """Runs stop, pushes are refused and every page turns read-only; the data is deleted 7
    days later unless resumed. Open streams end; members are asked again on their next
    request."""
    handle = _handle(request, icao)
    await tenants.suspend(
        _root(request),
        icao,
        by=operators.operator_by(op),
        reason=body.reason,
        space=handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).stop(icao, reason="suspended by an operator")
    _access(request).drop(icao=icao)
    return await _row(request, handle.record.airline_id)


@router.post("/tenants/{icao}/resume", response_model=AdminRow, dependencies=Csrf)
async def resume(icao: str, op: OperatorDep, request: Request) -> Response:
    """Back to SHADOW (never straight to LIVE), when a place is free."""
    handle = _handle(request, icao)
    registry = _registry(request)
    registry.require_memory()
    await tenants.resume(
        _root(request),
        icao,
        by=operators.operator_by(op),
        max_slots=request.app.state.settings.hosted_max_tenants,
        space=handle.space,
        at=wall_clock_now(),
    )
    await registry.start(icao)
    _access(request).drop(icao=icao)
    return await _row(request, handle.record.airline_id)


@router.post("/tenants/{icao}/delete-data", response_model=AdminRow, dependencies=Csrf)
async def delete_data(
    icao: str, body: ConfirmIcaoBody, op: OperatorDep, request: Request
) -> Response:
    """At least 7 days after the suspension (409 ``too_soon``), with the code typed: the
    airline's documents are purged in the background; its record stays as a tombstone."""
    handle = _handle(request, icao)
    if body.confirm_icao.strip().upper() != icao:
        raise ApiError(
            422,
            "confirm_icao",
            f"Type {icao} to confirm",
            problems=["confirm_icao: not this airline's code"],
        )
    await tenants.mark_deleting(
        _root(request), icao, by=operators.operator_by(op), at=wall_clock_now()
    )
    await _registry(request).reload(icao)
    _access(request).drop(icao=icao)
    return await _row(request, handle.record.airline_id)


@router.post("/tenants/{icao}/ops-manager-invite", response_model=OperatorLink, dependencies=Csrf)
async def ops_manager_invite(icao: str, op: OperatorDep, request: Request) -> Response:
    """The way out when an airline has no ops manager left: an ops-manager invite to its
    record holder's email (accepting it needs that account signed in)."""
    handle = _handle(request, icao)
    made, token = await members.ops_manager_invite(
        _root(request),
        icao,
        by_operator=operators.operator_by(op),
        space=handle.space,
        at=wall_clock_now(),
    )
    return _json(OperatorLink(link=f"{_origin(request)}/join#{token}", expires_at=made.expires_at))


@router.get("/tenants/{icao}/contact", response_model=AdminContact)
async def contact(icao: str, op: OperatorDep, request: Request) -> Response:
    handle = _handle(request, icao)
    try:
        record = await accounts.get_record(_root(request), handle.record.airline_id)
    except accounts.AirlineNotFound:
        raise ApiError(404, "not_found", "No such airline") from None
    return _json(operators.contact(record))
