"""Desk sessions (signed cookies), the login throttle, the CSRF guard and the task token.

The cookie is ``b64url(json{"n", "exp", "sid"}).b64url(hmac_sha256)`` keyed by
``TEPHRA_SESSION_SECRET``. It is HttpOnly and SameSite=Strict, and every state-changing desk
request must also be one a cross-site form cannot send (see :func:`require_csrf`).
"""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Final
from urllib.parse import urlsplit

from fastapi import Request, Response
from pydantic import SecretStr

from tephra.api import ApiError
from tephra.config import Settings
from tephra.models import SessionInfo
from tephra.util import timeutil

__all__ = [
    "COOKIE_NAME",
    "CSRF_HEADER",
    "TASK_HEADER",
    "LoginThrottle",
    "clear_session_cookie",
    "client_key",
    "desk_disabled_error",
    "desk_enabled",
    "is_https",
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
TASK_HEADER: Final = "X-Tephra-Task-Token"
CSRF_HEADER: Final = "X-Tephra-Desk"
MAX_TOKEN_CHARS: Final = 1024


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


def sign_session(name: str, settings: Settings, *, at: datetime) -> tuple[str, datetime]:
    """A session token for ``name`` and its expiry (whole seconds, UTC)."""
    if not _filled(settings.session_secret):
        raise ValueError("TEPHRA_SESSION_SECRET is blank; refusing to sign a desk session")
    expires_epoch = int((at + timedelta(hours=settings.desk_session_ttl_h)).timestamp())
    claims = {"n": name, "exp": expires_epoch, "sid": secrets.token_hex(8)}
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
    return SessionInfo(name=name, expires_at=expires_at)


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


def set_session_cookie(response: Response, token: str, settings: Settings, *, secure: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(settings.desk_session_ttl_h * 3600),
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
    """The dispatcher's session from the signed cookie; 401 without one."""
    await require_desk_enabled(request)
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    session = verify_session(token, settings, at=wall_clock_now()) if token else None
    if session is None:
        raise ApiError(401, "unauthenticated", "Desk login required")
    return session


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
