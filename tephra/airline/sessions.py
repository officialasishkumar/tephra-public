"""The airline workspace cookie, the feature gates and the signed-in airline dependency.

The cookie ``tephra_airline`` is ``b64url(json{"a", "k", "v", "exp", "c", "n"}).b64url(mac)``
with ``mac = HMAC-SHA256(key, payload)`` and ``key = HMAC-SHA256(session secret, label)``: the
label separates it from the Desk's cookie, so neither verifies as the other. Expiry is on the
wall clock, never the replay clock. Reading the claims costs no store read (the nav asks on
every page); :func:`require_airline` then checks them against the stored login.
"""

import base64
import hashlib
import hmac
import ipaddress
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from fastapi import Request, Response
from pydantic import ValidationError

from tephra.airline.models import AirlineLogin, AirlineRecord
from tephra.api import ApiError
from tephra.api.auth import client_key, is_https, wall_clock_now
from tephra.config import Settings
from tephra.store.base import Collection, Store

__all__ = [
    "COOKIE_NAME",
    "THROTTLES",
    "AirlineClaims",
    "AirlineContext",
    "accounts_enabled",
    "claims_of",
    "clear_airline_cookie",
    "client_key_64",
    "read_claims",
    "require_accounts",
    "require_airline",
    "require_onboard",
    "set_airline_cookie",
    "sign_claims",
    "verify_claims",
]

COOKIE_NAME: Final = "tephra_airline"
FEATURE: Final = "onboard"
MAX_COOKIE_CHARS: Final = 2048
NAME_CHARS: Final = 120
_KEY_LABEL: Final = b"tephra airline session v1"
THROTTLES: Final[dict[str, tuple[int, float]]] = {
    "airline_signup_attempts": (10, 3600.0),
    "airline_signups": (3, 86400.0),
    "airline_signups_all": (30, 86400.0),
    "airline_login": (5, 900.0),
    "airline_login_email": (10, 900.0),
    "airline_recover_email": (5, 3600.0),
    "airline_dry_runs": (30, 3600.0),
    "airline_writes": (100, 86400.0),
    "airline_writes_all": (3000, 86400.0),
    "airline_requests": (60, 300.0),
    "airline_requests_all": (5000, 86400.0),
}
"""``app.state`` name -> (tries, window in seconds). In process memory, which holds because
Cloud Run runs one instance; every count starts again after a deploy or restart. The writes
(saves of the draft, the answers or the assistant) are bounded per airline and for the whole
site, and every signed-in request (two store reads before anything else) per address and for
the whole site, so a cookie that costs only an email and a password cannot spend the store's
free daily reads or writes, which the shared site's audit trail needs too."""


@dataclass(frozen=True, slots=True)
class AirlineClaims:
    """What the cookie says. ``expires_at`` is read back from a cookie; :func:`sign_claims`
    signs a new expiry from its ``at``."""

    airline_id: str
    login_key: str
    version: int
    icao: str
    name: str
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AirlineContext:
    record: AirlineRecord
    login: AirlineLogin
    claims: AirlineClaims


def _filled(settings: Settings) -> bool:
    return bool(settings.session_secret.get_secret_value().strip())


def accounts_enabled(settings: Settings) -> bool:
    """Onboarding is shown and the cookie signer is set (as the Desk needs it)."""
    return FEATURE in settings.features and _filled(settings)


def _key(settings: Settings) -> bytes:
    secret = settings.session_secret.get_secret_value().encode("utf-8")
    return hmac.new(secret, _KEY_LABEL, hashlib.sha256).digest()


def _mac(payload: str, settings: Settings) -> bytes:
    return hmac.new(_key(settings), payload.encode("ascii"), hashlib.sha256).digest()


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def claims_of(record: AirlineRecord, login: AirlineLogin) -> AirlineClaims:
    """A draft has no checked ICAO or name yet: both are empty until it submits."""
    airline = None if record.answers is None else record.answers.airline
    return AirlineClaims(
        airline_id=record.id,
        login_key=login.login_key,
        version=login.session_version,
        icao="" if airline is None else airline.icao,
        name="" if airline is None else airline.name[:NAME_CHARS],
    )


def sign_claims(claims: AirlineClaims, settings: Settings, *, at: datetime) -> tuple[str, datetime]:
    """The cookie value for ``claims`` and its expiry (whole seconds, UTC)."""
    if not _filled(settings):
        raise ValueError("TEPHRA_SESSION_SECRET is blank; refusing to sign an airline session")
    expires = int((at + timedelta(hours=settings.airline_session_ttl_h)).timestamp())
    body = {
        "a": claims.airline_id,
        "k": claims.login_key,
        "v": claims.version,
        "exp": expires,
        "c": claims.icao,
        "n": claims.name[:NAME_CHARS],
    }
    payload = _b64encode(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    return f"{payload}.{_b64encode(_mac(payload, settings))}", datetime.fromtimestamp(expires, UTC)


def verify_claims(token: str, settings: Settings, *, at: datetime) -> AirlineClaims | None:
    """The claims a cookie value stands for, or None if it is malformed, forged or expired."""
    if not _filled(settings) or len(token) > MAX_COOKIE_CHARS or token.count(".") != 1:
        return None
    payload, _, signature = token.partition(".")
    try:
        if not hmac.compare_digest(_mac(payload, settings), _b64decode(signature)):
            return None
        body = json.loads(_b64decode(payload))
    except ValueError:
        return None
    return _claims(body, at)


def _claims(body: Any, at: datetime) -> AirlineClaims | None:
    if not isinstance(body, dict):
        return None
    texts = [body.get(key) for key in ("a", "k", "c", "n")]
    version, expires = body.get("v"), body.get("exp")
    if not all(isinstance(text, str) for text in texts) or not (texts[0] and texts[1]):
        return None
    if type(version) is not int or type(expires) is not int:
        return None
    try:
        expires_at = datetime.fromtimestamp(expires, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    if expires_at <= at:
        return None
    airline_id, login_key, icao, name = (str(text) for text in texts)
    return AirlineClaims(airline_id, login_key, version, icao, name, expires_at)


def read_claims(request: Request) -> AirlineClaims | None:
    """The signed-in airline's claims from the cookie alone (signature and wall-clock expiry)."""
    settings: Settings = request.app.state.settings
    token = request.cookies.get(COOKIE_NAME)
    if not token or not accounts_enabled(settings):
        return None
    return verify_claims(token, settings, at=wall_clock_now())


def set_airline_cookie(response: Response, request: Request, claims: AirlineClaims) -> None:
    settings: Settings = request.app.state.settings
    token, _ = sign_claims(claims, settings, at=wall_clock_now())
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(settings.airline_session_ttl_h * 3600),
        path="/",
        httponly=True,
        samesite="strict",
        secure=is_https(request),
    )


def clear_airline_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=is_https(request)
    )


def client_key_64(request: Request) -> str:
    """The throttles' client: the address, and an IPv6 address cut to its /64 (one host holds
    a whole /64 and could take a new address for every try)."""
    address = client_key(request)
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if parsed.version == 6:
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return address


# --- FastAPI dependencies ---------------------------------------------------------------


async def require_onboard(request: Request) -> None:
    """Onboarding is the one feature whose routes are refused when it is hidden: accounts and
    personal data must not be reachable on an instance that does not show them."""
    if FEATURE not in request.app.state.settings.features:
        raise ApiError(404, "feature_off", "Onboarding is off on this server")


async def require_accounts(request: Request) -> None:
    await require_onboard(request)
    if not _filled(request.app.state.settings):
        raise ApiError(503, "accounts_off", "Airline accounts need TEPHRA_SESSION_SECRET")


def _store(request: Request) -> Store:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    store: Store = runtime.store
    return store


async def require_airline(request: Request) -> AirlineContext:
    """The signed-in airline: the cookie checked against the stored login and record. A
    recovery or deletion bumps or removes the login, which signs every other browser out.
    The request throttles come before the two store reads, so a refused request costs none."""
    await require_accounts(request)
    claims = read_claims(request)
    if claims is None:
        raise _unauthenticated()
    _count_request(request)
    store = _store(request)
    login_doc = await store.get(Collection.AIRLINE_LOGINS, claims.login_key)
    record_doc = await store.get(Collection.AIRLINES, claims.airline_id)
    if login_doc is None or record_doc is None:
        raise _unauthenticated()
    try:
        login = AirlineLogin.model_validate(login_doc)
        record = AirlineRecord.model_validate(record_doc)
    except ValidationError:
        raise _unauthenticated() from None
    if login.session_version != claims.version or login.airline_id != record.id:
        raise _unauthenticated()
    return AirlineContext(record=record, login=login, claims=claims)


def _count_request(request: Request) -> None:
    state = request.app.state
    client = client_key_64(request)
    gates = [(state.airline_requests, client), (state.airline_requests_all, "site")]
    waits = [gate.retry_after_s(key) for gate, key in gates if gate.blocked(key)]
    if waits:
        raise ApiError(
            429,
            "too_many_requests",
            "Too many requests; try again later",
            headers={"Retry-After": str(max(waits))},
        )
    for gate, key in gates:
        gate.record_failure(key)


def _unauthenticated() -> ApiError:
    return ApiError(401, "unauthenticated", "Sign in to your airline workspace")
