"""Desk sessions (signed cookies), the login throttle, the CSRF guard and the task token.

The cookie is ``b64url(json{"n", "exp", "sid", "r"}).b64url(hmac_sha256)`` keyed by
``TEPHRA_SESSION_SECRET``. It is HttpOnly and SameSite=Strict, and every state-changing desk
request must also be one a cross-site form cannot send (see :func:`require_csrf`).

``r`` is the session's role: a dispatcher (the PIN) or a visitor (no PIN, REPLAY only, capped).
A token signed before roles existed carries no ``r`` and verifies as a dispatcher. The guards a
visitor meets live in :func:`require_desk`, matched on the request's method and path, so no
feature router needs to know about roles.
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import Counter, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final, get_args
from urllib.parse import urlsplit

from fastapi import Request, Response
from pydantic import SecretStr

from tephra.api import ApiError
from tephra.config import Settings
from tephra.models import RunMode, SessionInfo, SessionRole
from tephra.util import timeutil
from tephra.util.scope import current_tenant

__all__ = [
    "COOKIE_NAME",
    "CSRF_HEADER",
    "DISPATCHER_ONLY_PATHS",
    "TASK_HEADER",
    "VISITOR_ASK_PATHS",
    "VISITOR_DECISION_PATHS",
    "LoginThrottle",
    "actor_of",
    "clear_session_cookie",
    "client_key",
    "count_visitor_decision",
    "desk_disabled_error",
    "desk_enabled",
    "is_https",
    "new_session_id",
    "pin_matches",
    "require_csrf",
    "require_desk",
    "require_desk_enabled",
    "require_task_token",
    "set_session_cookie",
    "sign_session",
    "verify_session",
    "wall_clock_now",
]

COOKIE_NAME: Final = "tephra_desk"
TENANT_SCOPE_KEY: Final = "tephra.tenant"
"""``tephra.api.tenancy.SCOPE_KEY``: an ASGI scope rewritten from ``/a/<ICAO>/api``."""
TASK_HEADER: Final = "X-Tephra-Task-Token"
CSRF_HEADER: Final = "X-Tephra-Desk"
MAX_TOKEN_CHARS: Final = 1024
_DESK_ROLES: Final = frozenset(get_args(SessionRole)) - {"viewer"}
"""A Desk cookie is a dispatcher's or a visitor's; a viewer is only ever a hosted airline's
member, whose session comes from the airline cookie (``tephra.api.tenancy``)."""

DISPATCHER_ONLY_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/api/mode"),
    ("POST", "/api/desk/sample-feed"),
    ("POST", "/api/desk/connections"),
    ("POST", "/api/desk/upload"),
    ("POST", "/api/desk/notices"),
)
"""Method and path prefix of what changes the server's picture: a visitor is refused (403)."""
VISITOR_DECISION_PATHS: Final[tuple[tuple[str, str, str], ...]] = (
    ("POST", "/api/desk/advisories/", "/approve"),
    ("POST", "/api/desk/advisories/", "/edit"),
    ("POST", "/api/desk/advisories/", "/reject"),
    ("POST", "/api/desk/recovery/", "/approve"),
    ("POST", "/api/desk/recovery/", "/reject"),
    ("POST", "/api/desk/messages/", "/approve"),
    ("POST", "/api/desk/messages/", "/edit"),
    ("POST", "/api/desk/messages/", "/reject"),
    ("POST", "/api/desk/docs/", "/sign"),
    ("POST", "/api/desk/handover/", "/ack"),
)
"""Method, path prefix and suffix of every decision a visitor's cap counts (an id sits
between the two); a visitor may decide only while a replay plays."""
VISITOR_ASK_PATHS: Final[tuple[tuple[str, str], ...]] = (
    ("POST", "/api/desk/ask"),
    ("POST", "/api/desk/ask/voice"),
)
"""Method and exact path of a question to Ask TEPHRA (speaking a stored answer is not one)."""
VISITOR_ROLE_DETAIL: Final = "Visitors cannot do this; a dispatcher can."
VISITOR_REPLAY_ONLY_DETAIL: Final = "Visitors can decide only while a replay plays."
VISITOR_ASK_CAP_DETAIL: Final = "Visitors may ask three questions a session."


def wall_clock_now() -> datetime:
    """Sessions expire on wall-clock time; REPLAY moves ``timeutil.now()`` to the recording."""
    return timeutil.SystemClock().now()


def desk_enabled(settings: Settings) -> bool:
    """The desk needs a PIN and a session secret that are not blank.

    ``TEPHRA_DESK_PIN=`` (the line .env.example ships) parses to an empty secret, not None,
    and an empty signing key would let anyone who reads this module mint a session cookie.
    """
    return _filled(settings.desk_pin) and _filled(settings.session_secret)


def desk_disabled_error() -> ApiError:
    return ApiError(
        503,
        "desk_disabled",
        "The desk is disabled: TEPHRA_DESK_PIN or TEPHRA_SESSION_SECRET is not set",
    )


def _filled(secret: SecretStr | None) -> bool:
    return secret is not None and bool(secret.get_secret_value().strip())


# --- signed session tokens --------------------------------------------------------------


def session_ttl_h(settings: Settings, role: SessionRole) -> float:
    return settings.visitor_session_ttl_h if role == "visitor" else settings.desk_session_ttl_h


def new_session_id() -> str:
    return secrets.token_hex(8)


def sign_session(
    name: str,
    settings: Settings,
    *,
    at: datetime,
    role: SessionRole = "dispatcher",
    sid: str | None = None,
) -> tuple[str, datetime]:
    """A session token for ``name`` and its expiry (whole seconds, UTC); ``sid`` is the
    session id the token carries (a new one unless given)."""
    if not _filled(settings.session_secret):
        raise ValueError("TEPHRA_SESSION_SECRET is blank; refusing to sign a desk session")
    expires_epoch = int((at + timedelta(hours=session_ttl_h(settings, role))).timestamp())
    claims = {"n": name, "exp": expires_epoch, "sid": sid or new_session_id(), "r": role}
    payload = _b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    token = f"{payload}.{_b64encode(_mac(payload, settings))}"
    return token, datetime.fromtimestamp(expires_epoch, UTC)


def verify_session(token: str, settings: Settings, *, at: datetime) -> SessionInfo | None:
    """The session a token stands for, or None if it is malformed, forged or expired."""
    if not _filled(settings.session_secret):
        return None
    if len(token) > MAX_TOKEN_CHARS or token.count(".") != 1:
        return None
    payload, _, signature = token.partition(".")
    try:
        if not hmac.compare_digest(_mac(payload, settings), _b64decode(signature)):
            return None
        claims = json.loads(_b64decode(payload))
    except ValueError:
        return None
    if not isinstance(claims, dict):
        return None
    name, expires = claims.get("n"), claims.get("exp")
    if not isinstance(name, str) or not name or type(expires) is not int:
        return None
    try:
        expires_at = datetime.fromtimestamp(expires, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    if expires_at <= at:
        return None
    role, sid = claims.get("r", "dispatcher"), claims.get("sid")
    if role not in _DESK_ROLES or not isinstance(sid, str | None):
        return None
    if role == "visitor" and not sid:
        return None  # a visitor's caps are per session id; every minted visitor has one
    return SessionInfo(name=name, expires_at=expires_at, role=role, sid=sid or None)


def actor_of(session: SessionInfo) -> str:
    """The audit actor a session decides as: ``desk:<name>`` or ``visitor:<name>``; a hosted
    airline's member is ``desk:<name>#<member id>`` (names are unique only per airline)."""
    if session.role == "visitor":
        return f"visitor:{session.name}"
    if current_tenant() is not None and session.sid:
        return f"desk:{session.name}#{session.sid}"
    return f"desk:{session.name}"


def _mac(payload: str, settings: Settings) -> bytes:
    key = settings.session_secret.get_secret_value().encode("utf-8")
    return hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# --- cookies and request facts ----------------------------------------------------------


def is_https(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
    return request.url.scheme == "https" or forwarded == "https"


def client_key(request: Request) -> str:
    """The client address the login throttle counts against.

    Cloud Run's front end appends the address it accepted the connection from to
    ``X-Forwarded-For``; every entry to the left of it is whatever the caller sent. uvicorn
    runs with ``forwarded_allow_ips="*"`` and so reports the leftmost entry as the client,
    which a caller could change on every attempt. The rightmost entry is the one to count.
    """
    forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    if hops:
        return hops[-1]
    return request.client.host if request.client is not None else "unknown"


def set_session_cookie(
    response: Response,
    token: str,
    settings: Settings,
    *,
    secure: bool,
    role: SessionRole = "dispatcher",
) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(session_ttl_h(settings, role) * 3600),
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=secure)


def pin_matches(pin: str, settings: Settings) -> bool:
    if settings.desk_pin is None:
        return False
    expected = settings.desk_pin.get_secret_value().encode("utf-8")
    return hmac.compare_digest(pin.encode("utf-8"), expected)


# --- FastAPI dependencies ---------------------------------------------------------------


async def require_desk_enabled(request: Request) -> None:
    """503 ``desk_disabled`` before the body is validated: a switched-off desk says so first."""
    if not desk_enabled(request.app.state.settings):
        raise desk_disabled_error()


async def require_desk(request: Request) -> SessionInfo:
    """The session from the signed cookie; 401 without one. A visitor's session also meets
    the role guards here, before any route body runs: 403 ``visitor_role`` on what only a
    dispatcher may change, 403 ``visitor_replay_only`` on a decision outside REPLAY, 429
    ``visitor_cap`` / ``visitor_ask_cap`` once the session's caps are spent.

    Under a hosted airline (``/a/<ICAO>/api``) the session is the member's, which the
    airline dependency checked before this runs (``tephra.api.tenancy``): the Desk's PIN
    cookie is not used there."""
    if request.scope.get(TENANT_SCOPE_KEY) is not None:
        held = getattr(request.state, "tenant_scope", None)
        if held is None or held.session is None:
            raise ApiError(401, "unauthenticated", "Sign in to open this airline")
        session: SessionInfo = held.session
        return session
    await require_desk_enabled(request)
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    session = verify_session(token, settings, at=wall_clock_now()) if token else None
    if session is None:
        raise ApiError(401, "unauthenticated", "Desk login required")
    if session.role == "visitor":
        _guard_visitor(request, session, settings)
    return session


def _guard_visitor(request: Request, session: SessionInfo, settings: Settings) -> None:
    method, path = request.method.upper(), request.url.path
    if any(method == verb and _under(path, prefix) for verb, prefix in DISPATCHER_ONLY_PATHS):
        raise ApiError(403, "visitor_role", VISITOR_ROLE_DETAIL)
    decision = any(
        method == verb and _under(path, prefix) and path.endswith(suffix)
        for verb, prefix, suffix in VISITOR_DECISION_PATHS
    )
    asking = (method, path) in VISITOR_ASK_PATHS
    if (decision or asking) and _mode(request) is not RunMode.REPLAY:
        raise ApiError(403, "visitor_replay_only", VISITOR_REPLAY_ONLY_DETAIL)
    if decision:
        count_visitor_decision(request, session, settings)
    if asking:
        _count_visitor_ask(request, session, settings)


def _mode(request: Request) -> RunMode:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    return runtime.mode


def _under(path: str, prefix: str) -> bool:
    """``prefix`` names the path itself or a parent of it (never a longer sibling)."""
    return path == prefix or path.startswith(prefix if prefix.endswith("/") else prefix + "/")


def _sid(session: SessionInfo) -> str:
    assert session.sid is not None, "a visitor session always carries its id"
    return session.sid


def count_visitor_decision(request: Request, session: SessionInfo, settings: Settings) -> None:
    """One more decision for the session; 429 ``visitor_cap`` at ``visitor_decision_cap``."""
    decisions: Counter[str] = request.app.state.visitor_decisions
    key = _sid(session)
    if decisions[key] >= settings.visitor_decision_cap:
        raise ApiError(
            429,
            "visitor_cap",
            f"This visitor session has made its {settings.visitor_decision_cap} decisions. "
            "Enter again to continue.",
        )
    decisions[key] += 1


def _count_visitor_ask(request: Request, session: SessionInfo, settings: Settings) -> None:
    decisions: Counter[str] = request.app.state.visitor_decisions
    key = f"{_sid(session)}:ask"
    if decisions[key] >= settings.visitor_ask_cap:
        raise ApiError(429, "visitor_ask_cap", VISITOR_ASK_CAP_DETAIL)
    decisions[key] += 1


async def require_csrf(request: Request) -> None:
    """Refuse requests a cross-site page could forge.

    A JSON body or the ``X-Tephra-Desk: 1`` header both force a CORS preflight, which
    TEPHRA never answers, so either one proves the request came from our own pages. An
    ``Origin`` or ``Sec-Fetch-Site`` that names another site is refused outright.
    """
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise ApiError(403, "forbidden", "Cross-site request refused")
    origin = request.headers.get("origin")
    if origin is not None and urlsplit(origin).netloc != request.headers.get("host", ""):
        raise ApiError(403, "forbidden", "Cross-origin request refused")
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json" and request.headers.get(CSRF_HEADER) != "1":
        raise ApiError(
            403, "forbidden", f"Desk requests need a JSON body or the {CSRF_HEADER}: 1 header"
        )


async def require_task_token(request: Request) -> None:
    """403 unless ``X-Tephra-Task-Token`` equals ``TEPHRA_TASK_TOKEN`` (unset or blank: all)."""
    settings: Settings = request.app.state.settings
    supplied = request.headers.get(TASK_HEADER)
    if settings.task_token is None or not _filled(settings.task_token) or supplied is None:
        raise ApiError(403, "forbidden", "Task token missing or not configured")
    expected = settings.task_token.get_secret_value().encode("utf-8")
    if not hmac.compare_digest(supplied.encode("utf-8"), expected):
        raise ApiError(403, "forbidden", "Task token rejected")


# --- login throttle ---------------------------------------------------------------------


class LoginThrottle:
    """At most ``max_failures`` failed logins per client within ``window_s`` seconds.

    In process memory, which is enough because Cloud Run runs exactly one instance.
    ``max_clients`` bounds the table so a flood of addresses cannot grow it without limit.
    """

    def __init__(
        self,
        *,
        max_failures: int = 5,
        window_s: float = 600.0,
        max_clients: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_failures = max_failures
        self._window_s = window_s
        self._max_clients = max_clients
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}

    def blocked(self, client: str) -> bool:
        return len(self._recent(client)) >= self._max_failures

    def retry_after_s(self, client: str) -> int:
        recent = self._recent(client)
        if len(recent) < self._max_failures:
            return 0
        return max(1, int(recent[0] + self._window_s - self._clock()) + 1)

    def remaining(self, client: str) -> int:
        """Failures ``client`` may still make before it is blocked."""
        return max(0, self._max_failures - len(self._recent(client)))

    def record_failure(self, client: str) -> None:
        failures = self._failures.get(client)
        if failures is None:
            self._make_room()
            failures = self._failures[client] = deque()
        self._prune(failures)
        failures.append(self._clock())

    def clear(self, client: str) -> None:
        self._failures.pop(client, None)

    def _recent(self, client: str) -> deque[float]:
        failures = self._failures.get(client)
        if failures is None:
            return deque()
        self._prune(failures)
        return failures

    def _prune(self, failures: deque[float]) -> None:
        cutoff = self._clock() - self._window_s
        while failures and failures[0] <= cutoff:
            failures.popleft()

    def _make_room(self) -> None:
        if len(self._failures) < self._max_clients:
            return
        for failures in self._failures.values():
            self._prune(failures)
        for client in [key for key, failures in self._failures.items() if not failures]:
            del self._failures[client]
        while len(self._failures) >= self._max_clients:
            del self._failures[next(iter(self._failures))]
