"""Hosted airlines under ``/a/<ICAO>/``: the path rewrite, the route table and the one
dependency every API route carries when ``hosted`` is on.

An airline's API is the site's own routers reused: :class:`TenantPathMiddleware` turns
``/a/RFB/api/state`` into ``/api/state`` and marks the request with the airline, and
:func:`tenant_scope` then decides, before any route body runs, whether this person (or push
key) may use that route in that airline's state. A request without the mark is the demo's or
a root route's, and :func:`tenant_scope` answers None at once, so the demo is unchanged.

Routes are recognised by the identity of the route object, never by matching paths: inside an
included router a route's own ``path`` lacks the ``/api`` prefix (``ROUTE_INDEX``).
"""

import re
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Final, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.params import Depends as DependsParam
from fastapi.routing import APIRoute, iter_route_contexts
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tephra.airline.sessions import client_key_64, read_claims
from tephra.api import ApiError
from tephra.api.auth import TENANT_SCOPE_KEY
from tephra.models import Connection, ErrorBody, SessionInfo
from tephra.util import timeutil
from tephra.util.scope import Charge, bind_charge, bind_tenant

if TYPE_CHECKING:
    from tephra.api.auth import LoginThrottle
    from tephra.hosted.access import AccessCache
    from tephra.hosted.models import HostedRole, Member, TenantState
    from tephra.hosted.registry import TenantHandle, TenantRegistry
    from tephra.pipeline import Runtime

__all__ = [
    "ANY",
    "MAX_TENANT_LIMIT",
    "ROUTE_INDEX",
    "RUN",
    "SCOPE_KEY",
    "TENANT_ROUTES",
    "RouteRule",
    "TenantPathMiddleware",
    "TenantScope",
    "TenantScopeDep",
    "bind_wall_clock",
    "build_route_index",
    "gate",
    "require_scope",
    "scoped_routes_missing",
    "tenant_scope",
]

SCOPE_KEY: Final = TENANT_SCOPE_KEY
"""The ASGI scope key the middleware sets to the airline's ICAO on a rewritten API request."""
PAGE_KEY: Final = "tephra.tenant_page"
"""Set to the ICAO on a page request under ``/a/<ICAO>/`` (the page routes read it)."""
REFUSED_KEY: Final = "tephra.tenant_refused"
"""Set on an ``/a/`` path the middleware refused; it is left unrewritten and answers 404."""
MAX_TENANT_LIMIT: Final = 50
"""``limit`` above this answers 422 under ``/a/`` (a list read costs one read per entry)."""

_ICAO: Final = re.compile(r"[A-Z]{3}")
_TENANT_PATH: Final = re.compile(r"^/a/([^/]*)(/.*)?$")
_TRICKS: Final = (b"//", b"/./", b"/../", b"%2e", b"%2f", b"%5c", b"\\")

type Need = Literal["viewer", "dispatcher", "ops_manager", "key"]

RUN: Final = frozenset({"shadow", "live"})
ANY: Final = frozenset({"setup", "shadow", "live", "suspended"})
SETUP_RUN: Final = frozenset({"setup", "shadow", "live"})
SETUP: Final = frozenset({"setup"})
SHADOW: Final = frozenset({"shadow"})
LIVE: Final = frozenset({"live"})
_RANK: Final = {"viewer": 0, "dispatcher": 1, "ops_manager": 2}
"""``tephra.hosted.models.ROLE_RANK``, kept here so the demo's import path stays free of the
hosted package (``tests/test_tenancy_routes.py`` checks the two agree)."""
ROLE_WORDS: Final = {"viewer": "Viewer", "dispatcher": "Dispatcher", "ops_manager": "Ops manager"}


@dataclass(frozen=True, slots=True)
class RouteRule:
    need: Need
    states: frozenset[str]


def _rules(
    method: str, paths: tuple[str, ...], need: Need, states: frozenset[str]
) -> dict[tuple[str, str], RouteRule]:
    return {(method, path): RouteRule(need, states) for path in paths}


_ADVISORY: Final = "/api/desk/advisories/{advisory_id}"
_MESSAGE: Final = "/api/desk/messages/{message_id}"
_REPORT: Final = "/api/desk/crew-reports/{report_id}"
_KEY: Final = "/api/tenant/keys/{connection_id}"

TENANT_ROUTES: Final[dict[tuple[str, str], RouteRule]] = {
    # the site's own routes, reused on the airline's runtime (SPEC §4.2)
    **_rules(
        "GET",
        (
            "/api/state",
            "/api/wall",
            "/api/advisories",
            "/api/advisories/{advisory_id}/chain",
            "/api/audit",
            "/api/outbound",
            "/api/feeds",
            "/api/policy",
            "/api/routes/{origin_icao}/{dest_icao}",
            "/api/airports",
            "/api/events",
            "/api/stream",
            "/api/budget",
            "/api/duty",
            "/api/notices",
            "/api/docs",
            "/api/docs/{doc_id}",
            "/api/connect/live",
            "/api/fleet",
            "/api/desk/advisories",
            "/api/desk/ai-failures",
            "/api/desk/messages",
            "/api/desk/handovers",
            "/api/desk/handover/{handover_id}",
            "/api/desk/crew-reports",
            "/api/desk/crew-reports/fix",
        ),
        "viewer",
        RUN,
    ),
    **_rules(
        "GET", ("/api/connect/format", "/api/connect/schema.json", "/api/desk/me"), "viewer", ANY
    ),
    **_rules(
        "POST",
        (
            f"{_ADVISORY}/approve",
            f"{_ADVISORY}/edit",
            f"{_ADVISORY}/reject",
            "/api/desk/ai-failures/{failure_id}/handled",
            "/api/desk/ask",
            "/api/desk/notices",
            "/api/desk/messages/draft",
            f"{_MESSAGE}/approve",
            f"{_MESSAGE}/edit",
            f"{_MESSAGE}/reject",
            "/api/desk/handover",
            "/api/desk/handover/{handover_id}/ack",
            "/api/desk/docs/sra",
            "/api/desk/docs/var",
            "/api/desk/docs/{doc_id}/sign",
            "/api/desk/crew-reports",
            f"{_REPORT}/withdraw",
            f"{_REPORT}/message",
        ),
        "dispatcher",
        RUN,
    ),
    **_rules("POST", ("/api/desk/upload",), "ops_manager", RUN),
    **_rules("POST", ("/api/push/positions",), "key", SETUP_RUN),
    # the airline's own routes (routes_tenant.py)
    **_rules(
        "GET",
        (
            "/api/tenant/header",
            "/api/tenant/golive",
            "/api/tenant/feeds",
            "/api/tenant/policy",
            "/api/tenant/assistant",
            "/api/tenant/people",
            "/api/tenant/record",
        ),
        "viewer",
        ANY,
    ),
    **_rules("GET", ("/api/tenant/keys", "/api/tenant/record/export"), "ops_manager", ANY),
    **_rules("POST", ("/api/tenant/start",), "ops_manager", SETUP),
    **_rules("POST", ("/api/tenant/live",), "ops_manager", SHADOW),
    **_rules("POST", ("/api/tenant/shadow",), "ops_manager", LIVE),
    **_rules("POST", ("/api/tenant/stop",), "ops_manager", RUN),
    **_rules("POST", ("/api/tenant/feeds/dry-run",), "dispatcher", SETUP_RUN),
    **_rules(
        "POST",
        (
            "/api/tenant/keys",
            f"{_KEY}/rotate",
            f"{_KEY}/revoke",
            "/api/tenant/policy",
            "/api/tenant/policy/confirm",
            "/api/tenant/policy/sra",
            "/api/tenant/policy/sra/withdraw",
            "/api/tenant/people/invites",
            "/api/tenant/people/invites/{invite_id}/revoke",
            "/api/tenant/people/{member_id}/role",
            "/api/tenant/people/{member_id}/remove",
        ),
        "ops_manager",
        SETUP_RUN,
    ),
    **_rules(
        "PUT", ("/api/tenant/assistant", "/api/tenant/assistant/key"), "ops_manager", SETUP_RUN
    ),
    **_rules("DELETE", ("/api/tenant/assistant/key",), "ops_manager", SETUP_RUN),
    **_rules("POST", ("/api/tenant/people/me/leave",), "viewer", ANY),
    **_rules("POST", ("/api/tenant/record/check",), "ops_manager", ANY),
}
"""(method, full path template) -> who may call it under ``/a/<ICAO>/api`` and in which
states. Everything else answers 404 ``not_hosted`` there (SPEC §4.2)."""

ROUTE_INDEX: Final[dict[int, tuple[str, str]]] = {}
"""``id(route object)`` -> (method, full path template), filled by :func:`build_route_index`
once the app has every router. The route objects are module-level, so the index holds for
every app built in this process."""


# --- the path rewrite -------------------------------------------------------------------


class TenantPathMiddleware:
    """``/a/<ICAO>/api/...`` becomes ``/api/...`` with the scope marked; every other
    ``/a/<ICAO>/...`` path is a page and passes unchanged. Both run with the airline and the
    wall clock bound, so nothing the request does reads the demo's replay clock.

    An ``/a/`` path with an encoded or relative step in it, or whose code is not three
    capital letters, is marked refused and left as it is: no route answers it (404)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/a" or path.startswith("/a/")):
            await self.app(scope, receive, send)
            return
        icao, rest = _split(scope)
        if icao is None:
            await self.app({**scope, REFUSED_KEY: True}, receive, send)
            return
        if rest == "/api" or rest.startswith("/api/"):
            if rest.endswith("/") or rest in _UNSCOPED:
                # Rewritten, a trailing slash would be redirected to the demo's path (Starlette
                # builds the redirect from the rewritten path), and the schema is the site's,
                # not an airline route: left as they are, no route answers them (404).
                await self.app({**scope, REFUSED_KEY: True}, receive, send)
                return
            raw: bytes = scope.get("raw_path") or scope["path"].encode("utf-8")
            raw_rest = raw[len(f"/a/{icao}") :]
            scope = {**scope, "path": rest, "raw_path": raw_rest, SCOPE_KEY: icao}
            send = _no_method_hints(send)
        else:
            scope = {**scope, PAGE_KEY: icao}
        with (
            bind_tenant(icao),
            timeutil.bind_clock(timeutil.SystemClock()),
            bind_charge() as charge,
        ):
            await self.app({**scope, CHARGE_KEY: charge}, receive, send)


NOT_HOSTED_DETAIL: Final = "Not part of TEPHRA for an airline"
_NOT_HOSTED_BODY: Final = (
    ErrorBody(error="not_hosted", detail=NOT_HOSTED_DETAIL).model_dump_json().encode()
)
_UNSCOPED: Final = frozenset({"/api/openapi.json"})
"""Paths under ``/api`` that are not API routes (no :func:`tenant_scope`): 404 under ``/a/``."""
CHARGE_KEY: Final = "tephra.tenant_charge"
"""The request's :class:`~tephra.util.scope.Charge` (set by the middleware on ``/a/`` paths)."""


def _no_method_hints(send: Send) -> Send:
    """A 405 under ``/a/<ICAO>/api`` would tell which site routes exist with another method;
    it answers as every route outside the airline table does (404 ``not_hosted``)."""
    replacing = False

    async def guarded(message: Message) -> None:
        nonlocal replacing
        if message["type"] == "http.response.start" and message["status"] == 405:
            replacing = True
            headers = [
                (name, value)
                for name, value in message.get("headers", [])
                if name.lower() not in {b"content-length", b"content-type", b"allow"}
            ]
            headers += [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_NOT_HOSTED_BODY)).encode()),
            ]
            await send({**message, "status": 404, "headers": headers})
            return
        if replacing and message["type"] == "http.response.body":
            if not message.get("more_body", False):
                await send({"type": "http.response.body", "body": _NOT_HOSTED_BODY})
            return
        await send(message)

    return guarded


def _split(scope: Scope) -> tuple[str | None, str]:
    """The airline code and the path after it, or (None, "") for a path that is refused."""
    path: str = scope["path"]
    raw: bytes = scope.get("raw_path") or path.encode("utf-8")
    lowered = raw.lower()
    if any(trick in lowered for trick in _TRICKS) or lowered.endswith((b"/.", b"/..")):
        return None, ""
    match = _TENANT_PATH.match(path)
    if match is None or _ICAO.fullmatch(match[1]) is None:
        return None, ""
    icao = match[1]
    if not raw.startswith(f"/a/{icao}".encode()):
        return None, ""  # the code itself was percent-encoded
    return icao, match[2] or ""


# --- the route index --------------------------------------------------------------------


def _api_contexts(app: FastAPI) -> Iterator[tuple[APIRoute, str, list[DependsParam]]]:
    for context in iter_route_contexts(app.routes):
        route = context.original_route
        if isinstance(route, APIRoute):
            yield route, str(context.path_format), list(context.dependencies or [])


def build_route_index(app: FastAPI) -> dict[int, tuple[str, str]]:
    """Every API route's (method, full path template), keyed by the route object's id."""
    index: dict[int, tuple[str, str]] = {}
    for route, path, _ in _api_contexts(app):
        methods = sorted(route.methods or ())
        if len(methods) != 1:
            raise RuntimeError(f"{path}: an API route takes exactly one method")
        index[id(route)] = (methods[0], path)
    ROUTE_INDEX.update(index)
    return index


def scoped_routes_missing(app: FastAPI) -> list[str]:
    """``METHOD /path`` of every ``/api`` or ``/tasks`` route that lacks :func:`tenant_scope`
    (``create_app`` refuses to start while any is listed)."""
    missing = []
    for route, path, dependencies in _api_contexts(app):
        if not path.startswith(("/api/", "/tasks/")):
            continue
        if not any(d.dependency is tenant_scope for d in dependencies):
            missing.append(f"{','.join(sorted(route.methods or ()))} {path}")
    return missing


# --- the dependency ---------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TenantScope:
    """Who is asking, for which airline. ``member``, ``role`` and ``session`` are None for a
    push (its key is the caller); ``connection`` is the push key's connection."""

    icao: str
    handle: "TenantHandle"
    member: "Member | None"
    role: "HostedRole | None"
    session: SessionInfo | None
    login_key: str | None = None
    version: int | None = None
    connection: Connection | None = field(default=None)

    @property
    def runtime(self) -> "Runtime | None":
        return self.handle.runtime

    @property
    def name(self) -> str:
        return str(self.handle.record.name)


def _registry(request: Request) -> "TenantRegistry":
    registry: TenantRegistry | None = getattr(request.app.state, "registry", None)
    if registry is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    return registry


def gate(request: Request, name: str, key: str, error: str, detail: str) -> None:
    """Count one more against throttle ``name`` for ``key``; 429 once it is spent."""
    throttle: LoginThrottle = getattr(request.app.state, name)
    if throttle.blocked(key):
        raise ApiError(
            429, error, detail, headers={"Retry-After": str(throttle.retry_after_s(key))}
        )
    throttle.record_failure(key)


def _no_such_airline() -> ApiError:
    return ApiError(404, "no_such_airline", "No such airline")


def _bad_key() -> ApiError:
    return ApiError(401, "bad_key", "A live push key for this airline is required")


async def tenant_scope(request: Request) -> TenantScope | None:
    """None for every request outside ``/a/<ICAO>/api``. Inside, in this order: the route is
    one an airline may use (404 ``not_hosted``); the caller is a live push key (the push) or
    a signed-in member of this airline (401, 404 ``no_such_airline``); the airline's state
    allows the route (403 ``tenant_suspended``, 409 ``not_started`` / ``wrong_state``); the
    member's role is enough (403 ``role``); ``limit`` is at most 50 (422)."""
    icao: str | None = request.scope.get(SCOPE_KEY)
    if icao is None:
        return None
    route = request.scope.get("route")
    key = ROUTE_INDEX.get(id(route)) if route is not None else None
    rule = TENANT_ROUTES.get(key) if key is not None else None
    if rule is None:
        raise ApiError(404, "not_hosted", NOT_HOSTED_DETAIL)
    registry = _registry(request)
    if rule.need == "key":
        return _push_scope(request, registry, icao, rule)
    claims = read_claims(request)
    if claims is None:
        raise ApiError(401, "unauthenticated", "Sign in to open this airline")
    gate(
        request,
        "hosted_member_requests",
        f"{icao}~{claims.login_key}",
        "too_many_requests",
        "Too many requests; try again later",
    )
    handle = registry.handle(icao)
    if handle is None:
        raise _no_such_airline()
    access: AccessCache = request.app.state.access
    if not access.holds_member(claims.login_key, icao):
        _count_miss(request)
    member = await access.member(
        request.app.state.runtime.store,
        claims.login_key,
        claims.version,
        icao,
        record=handle.record,
    )
    if member is None:
        raise _no_such_airline()
    charge: Charge | None = request.scope.get(CHARGE_KEY)
    if charge is not None:
        charge.icao = icao  # from here on, root-store use is this airline's
    _check_state(handle, rule)
    _check_role(handle, member, rule)
    _check_limit(request)
    _check_reads_left(request, icao, key)
    expires_at = claims.expires_at
    assert expires_at is not None, "claims read from a cookie carry their expiry"
    session = SessionInfo(
        name=member.display_name,
        expires_at=expires_at,
        role="viewer" if member.role == "viewer" else "dispatcher",
        sid=member.id,
    )
    found = TenantScope(
        icao=icao,
        handle=handle,
        member=member,
        role=member.role,
        session=session,
        login_key=claims.login_key,
        version=claims.version,
    )
    request.state.tenant_scope = found  # the Desk session dependency reads it
    return found


def _count_miss(request: Request) -> None:
    """A member looked up in the store (not the access cache) costs reads: it counts against
    the address's signed-in request throttle. Never against a site-wide count, which anyone
    with a self-made account could spend to lock every airline's people out; the login's own
    ``hosted_member_requests`` was counted before this."""
    gate(
        request,
        "airline_requests",
        client_key_64(request),
        "too_many_requests",
        "Too many requests; try again later",
    )


def _push_scope(
    request: Request, registry: "TenantRegistry", icao: str, rule: RouteRule
) -> TenantScope:
    """The push key from ``Authorization`` alone, through the registry's in-memory index: no
    store read. An unknown airline, a suspended or deleted one, no key and a wrong key all
    get the same 401, and each such try counts against the client."""
    client = client_key_64(request)
    throttle: LoginThrottle = request.app.state.push_bad_key
    if throttle.blocked(client):
        raise ApiError(
            429,
            "too_many_attempts",
            "Too many pushes with a bad key; try again later",
            headers={"Retry-After": str(throttle.retry_after_s(client))},
        )
    scheme, _, given = (request.headers.get("authorization") or "").partition(" ")
    key = given.strip() if scheme.lower() == "bearer" else ""
    connection = registry.push_key(icao, key) if key else None
    handle = registry.handle(icao) if connection is not None else None
    if connection is None or handle is None or handle.record.state not in rule.states:
        throttle.record_failure(client)
        raise _bad_key()
    if handle.record.state in RUN:
        _check_paused(request, icao)
    return TenantScope(
        icao=icao, handle=handle, member=None, role=None, session=None, connection=connection
    )


def _check_paused(request: Request, icao: str) -> None:
    settings = request.app.state.settings
    meter = request.app.state.meter
    if meter.site_over(settings) is not None:
        raise ApiError(
            503, "site_paused", "Paused: the shared site's free daily database allowance is used"
        )
    if meter.over(icao, settings) is not None:
        raise ApiError(
            503,
            "airline_paused",
            "Paused: this airline's share of the free daily allowance is used",
        )


def _check_state(handle: "TenantHandle", rule: RouteRule) -> None:
    state: TenantState = handle.record.state
    if state in rule.states:
        return
    if state in {"deleting", "deleted"}:
        raise _no_such_airline()
    if state == "suspended":
        raise ApiError(
            403, "tenant_suspended", f"TEPHRA's operators suspended {handle.record.name}"
        )
    if state == "setup" and rule.states == RUN:
        raise ApiError(409, "not_started", f"TEPHRA has not started for {handle.record.name} yet")
    raise ApiError(409, "wrong_state", f"Not possible while {handle.record.name} is {state}")


def _check_role(handle: "TenantHandle", member: "Member", rule: RouteRule) -> None:
    if _RANK[member.role] >= _RANK[rule.need]:
        return
    if rule.need == "ops_manager":
        raise ApiError(403, "role", "Only an ops manager can do this.")
    raise ApiError(
        403,
        "role",
        f"Your role in {handle.record.name} is {ROLE_WORDS[member.role]}. "
        "Ops managers and dispatchers decide.",
    )


_READS_ALWAYS: Final = frozenset({("GET", "/api/tenant/header")})
"""What a member may still read once the airline's reads are spent: the header says why."""


def _check_reads_left(request: Request, icao: str, key: tuple[str, str] | None) -> None:
    """Once an airline has read up to its ceiling today, its people's reads are refused
    (503 ``airline_paused``) until 00:00 Pacific: the airlines together never pass the site's
    cap. Decisions (writes) still go through, and the header still answers."""
    if request.method not in {"GET", "HEAD"} or key in _READS_ALWAYS:
        return
    meter = request.app.state.meter
    if meter.reads_spent(icao, request.app.state.settings):
        raise ApiError(
            503,
            "airline_paused",
            "Paused: this airline's share of the free daily database reads is used. "
            "Resumes 00:00 Pacific (07:00 UTC).",
        )


def _limit_value(raw: str) -> float | None:
    """``limit`` as FastAPI will read it (it accepts "+200", " 200", "200.0", and digits of
    other scripts)."""
    text = raw.strip()
    try:
        return float(int(text))
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return None


def _check_limit(request: Request) -> None:
    raw = request.query_params.get("limit")
    value = None if raw is None else _limit_value(raw)
    if value is not None and value > MAX_TENANT_LIMIT:
        raise ApiError(
            422,
            "limit_too_large",
            f"At most {MAX_TENANT_LIMIT} entries a page for an airline",
            problems=[f"limit: at most {MAX_TENANT_LIMIT}"],
        )


TenantScopeDep = Annotated[TenantScope | None, Depends(tenant_scope)]


async def bind_wall_clock() -> AsyncIterator[None]:
    """A router dependency of the root hosted, operator and operator-task routes: what they
    stamp is wall time, whatever clock the demo plays (rule 11)."""
    with timeutil.bind_clock(timeutil.SystemClock()):
        yield


async def require_scope(scope: TenantScopeDep) -> TenantScope:
    """The airline's own routes exist only under ``/a/<ICAO>/api`` (404 at the root)."""
    if scope is None:
        raise ApiError(404, "not_found", "Not found")
    return scope
