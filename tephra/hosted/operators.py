"""TEPHRA staff ("operators" in code): the people who verify the airlines that onboard and,
where the site hosts airlines, approve hosting, suspend, resume and delete (D9). Never an airline
member and never a Desk role.

The first operator comes from a one-time link minted with the task token, which works only
while no active operator exists (S10); every later one is invited by an operator. Passwords are
scrypt, as airline accounts'. The cookie ``tephra_operator`` is
``b64url(json{"k", "v", "n", "exp"}).b64url(mac)`` with its own MAC label, so it never verifies
as an airline's or the Desk's; it is checked against the operator document on every request
(through the access cache, which every function here empties for the operator it changes).
"""

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import quote

from fastapi import Request, Response
from pydantic import ValidationError

from tephra.airline import passwords
from tephra.airline.models import AirlineRecord, Stamp
from tephra.config import Settings
from tephra.hosted.access import AccessCache
from tephra.hosted.members import email_hint
from tephra.hosted.models import (
    AdminContact,
    HostedRefused,
    Operator,
    OperatorInvite,
    OperatorInviteView,
    OperatorView,
)
from tephra.store.base import Collection, Store
from tephra.util import timeutil

__all__ = [
    "COOKIE_NAME",
    "INVITE_LIFE",
    "SESSION_TTL",
    "OperatorClaims",
    "accept_invite",
    "bootstrap_invite",
    "check_sign_in",
    "clear_operator_cookie",
    "contact",
    "disable",
    "find_by_k",
    "get_operator",
    "invite",
    "invite_lookup",
    "invite_view",
    "issue_operator_cookie",
    "list_operators",
    "login_key",
    "note_sign_in",
    "operator_by",
    "operator_view",
    "read_operator_claims",
    "revoke",
    "short_key",
    "sign_out",
]

COOKIE_NAME: Final = "tephra_operator"
SESSION_TTL: Final = timedelta(hours=8)
INVITE_LIFE: Final = timedelta(hours=24)
MAX_COOKIE_CHARS: Final = 1024
_MAC_LABEL: Final = b"tephra operator session v1"
_LOGIN_LABEL: Final = "tephra.operator/1|"


def login_key(email: str) -> str:
    return hashlib.sha256((_LOGIN_LABEL + email.strip().lower()).encode("utf-8")).hexdigest()


def short_key(op: Operator) -> str:
    """The id operator routes and pages use (``/api/admin/operators/{k}/disable``)."""
    return op.login_key[:12]


def operator_by(op: Operator) -> str:
    """The stamp and audit actor of an operator: ``operator:<name>#<k[:8]>``."""
    return f"operator:{op.name}#{op.login_key[:8]}"


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _parse(doc: Any) -> Operator | None:
    if doc is None:
        return None
    try:
        return Operator.model_validate(doc)
    except ValidationError:
        return None


# --- reads ------------------------------------------------------------------------------


async def get_operator(store: Store, key: str) -> Operator | None:
    return _parse(await store.get(Collection.OPERATORS, key))


async def list_operators(store: Store) -> list[Operator]:
    docs = await store.list_docs(Collection.OPERATORS, limit=100)
    found = [op for doc in docs if (op := _parse(doc)) is not None]
    return sorted(found, key=lambda op: (op.created_at, op.login_key))


async def find_by_k(store: Store, k: str) -> Operator | None:
    return next((op for op in await list_operators(store) if short_key(op) == k), None)


def operator_view(op: Operator, *, you: Operator | None) -> OperatorView:
    return OperatorView(
        name=op.name,
        email=op.email,
        k=short_key(op),
        created_at=op.created_at,
        last_sign_in_at=op.last_sign_in_at,
        you=you is not None and you.login_key == op.login_key,
        disabled=op.disabled,
    )


# --- invites ----------------------------------------------------------------------------


async def _put_invite(
    store: Store, name: str, email: str, created_by: str | None, *, at: datetime
) -> str:
    token = secrets.token_urlsafe(32)
    made = OperatorInvite(
        email=email.strip().lower(),
        name=" ".join(name.split()),
        created_by=created_by,
        created_at=at,
        expires_at=at + INVITE_LIFE,
    )

    def create(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is not None:
            raise RuntimeError("an operator invite token was drawn twice")
        return made.model_dump(mode="json")

    await store.update(Collection.OPERATOR_INVITES, _sha(token), create)
    return token


async def _any_active(store: Store) -> bool:
    return any(op.disabled is None for op in await list_operators(store))


async def bootstrap_invite(store: Store, name: str, email: str, *, at: datetime) -> str:
    """The first operator's one-time link (``/tasks/operator-invite``): refused with 409
    ``operators_exist`` once any operator is active."""
    if await _any_active(store):
        raise HostedRefused(409, "operators_exist", "TEPHRA staff exist: one of them invites you")
    return await _put_invite(store, name, email, None, at=at)


async def invite(store: Store, name: str, email: str, *, by: Operator, at: datetime) -> str:
    existing = await get_operator(store, login_key(email))
    if existing is not None and existing.disabled is None:
        raise HostedRefused(409, "email_taken", "That email already has a TEPHRA staff account")
    return await _put_invite(store, name, email, by.login_key[:8], at=at)


async def invite_lookup(store: Store, token: str) -> OperatorInvite | None:
    doc = await store.get(Collection.OPERATOR_INVITES, _sha(token))
    return None if doc is None else OperatorInvite.model_validate(doc)


def _usable(found: OperatorInvite | None, at: datetime) -> bool:
    return found is not None and found.used_at is None and found.expires_at > at


def _gone() -> HostedRefused:
    return HostedRefused(404, "invite_gone", "This link is used or expired")


async def invite_view(store: Store, token: str, *, at: datetime) -> OperatorInviteView:
    found = await invite_lookup(store, token)
    if found is None or not _usable(found, at):
        raise _gone()
    return OperatorInviteView(
        name=found.name, email_hint=email_hint(found.email), expires_at=found.expires_at
    )


async def accept_invite(
    store: Store, token: str, email: str, password: str, *, access: AccessCache, at: datetime
) -> Operator:
    """The operator account for the invited email (403 ``wrong_email`` for another one). A
    bootstrap link is refused once another operator became active meanwhile."""
    found = await invite_lookup(store, token)
    if found is None or not _usable(found, at):
        raise _gone()
    email = email.strip().lower()
    if email != found.email:
        raise HostedRefused(403, "wrong_email", "This link is for another email address")
    if found.created_by is None and await _any_active(store):
        raise _gone()
    key = login_key(email)
    hashed = await passwords.hashed(password)

    def use(stored: dict[str, Any] | None) -> dict[str, Any]:
        current = None if stored is None else OperatorInvite.model_validate(stored)
        if current is None or not _usable(current, at):
            raise _gone()
        return current.model_copy(update={"used_at": at}).model_dump(mode="json")

    await store.update(Collection.OPERATOR_INVITES, _sha(token), use)

    def create(stored: dict[str, Any] | None) -> dict[str, Any]:
        held = _parse(stored)
        if held is not None and held.disabled is None:
            raise HostedRefused(409, "email_taken", "That email already has a TEPHRA staff account")
        return Operator(
            login_key=key,
            email=email,
            name=found.name,
            password=hashed,
            session_version=1 if held is None else held.session_version + 1,
            created_at=at,
            last_sign_in_at=at,
        ).model_dump(mode="json")

    made = Operator.model_validate(await store.update(Collection.OPERATORS, key, create))
    access.drop(login_key=key)
    return made


# --- sessions ---------------------------------------------------------------------------


async def check_sign_in(store: Store, email: str, password: str) -> Operator | None:
    """The active operator these credentials open, or None; an unknown email costs one
    scrypt too, so the time does not tell whether it exists."""
    found = await get_operator(store, login_key(email))
    matched = await passwords.check_password(password, None if found is None else found.password)
    if found is None or not matched or found.disabled is not None:
        return None
    return found


async def note_sign_in(store: Store, op: Operator, *, at: datetime) -> Operator:
    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        held = _parse(stored)
        if held is None:
            raise HostedRefused(401, "unauthenticated", "Sign in as TEPHRA staff")
        return held.model_copy(update={"last_sign_in_at": at}).model_dump(mode="json")

    return Operator.model_validate(await store.update(Collection.OPERATORS, op.login_key, change))


async def _bump(store: Store, key: str, *, disabled: Stamp | None = None) -> Operator:
    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        held = _parse(stored)
        if held is None:
            raise HostedRefused(404, "not_found", "No such staff account")
        update: dict[str, Any] = {"session_version": held.session_version + 1}
        if disabled is not None:
            update["disabled"] = held.disabled or disabled
        return held.model_copy(update=update).model_dump(mode="json")

    return Operator.model_validate(await store.update(Collection.OPERATORS, key, change))


async def sign_out(store: Store, key: str, *, access: AccessCache) -> None:
    """Every browser of this operator is signed out (a new session version)."""
    try:
        await _bump(store, key)
    finally:
        access.drop(login_key=key)


async def disable(
    store: Store, key: str, *, by: Operator, access: AccessCache, at: datetime
) -> list[Operator]:
    """Refused (409 ``last_operator``) for the last active operator."""
    others = [op for op in await list_operators(store) if op.disabled is None]
    if [op.login_key for op in others] == [key]:
        raise HostedRefused(409, "last_operator", "The last active staff account stays")
    try:
        await _bump(store, key, disabled=Stamp(by=operator_by(by), at=at))
    finally:
        access.drop(login_key=key)
    return await list_operators(store)


async def revoke(store: Store, email: str, *, access: AccessCache, at: datetime) -> Operator:
    """``/tasks/operator-revoke``: the kill switch, with the task token (the last operator
    too: a new one is bootstrapped after)."""
    key = login_key(email)
    try:
        return await _bump(store, key, disabled=Stamp(by="task token", at=at))
    finally:
        access.drop(login_key=key)


@dataclass(frozen=True, slots=True)
class OperatorClaims:
    login_key: str
    version: int
    name: str
    expires_at: datetime


def _mac(payload: str, settings: Settings) -> bytes:
    secret = settings.session_secret.get_secret_value().encode("utf-8")
    key = hmac.new(secret, _MAC_LABEL, hashlib.sha256).digest()
    return hmac.new(key, payload.encode("ascii"), hashlib.sha256).digest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_operator_cookie(
    response: Response, op: Operator, settings: Settings, *, secure: bool
) -> datetime:
    """Sets the cookie (8 h on the wall clock) and returns its expiry."""
    if not settings.session_secret.get_secret_value().strip():
        raise ValueError("TEPHRA_SESSION_SECRET is blank; refusing to sign an operator session")
    expires = int((timeutil.SystemClock().now() + SESSION_TTL).timestamp())
    body = {"k": op.login_key, "v": op.session_version, "n": op.name, "exp": expires}
    payload = _b64(json.dumps(body, separators=(",", ":")).encode("utf-8"))
    response.set_cookie(
        COOKIE_NAME,
        f"{payload}.{_b64(_mac(payload, settings))}",
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )
    return datetime.fromtimestamp(expires, UTC)


def clear_operator_cookie(response: Response, *, secure: bool) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="strict", secure=secure)


def read_operator_claims(request: Request, settings: Settings) -> OperatorClaims | None:
    """The cookie's claims (signature and wall-clock expiry; no store read), or None."""
    token = request.cookies.get(COOKIE_NAME)
    if not token or not settings.session_secret.get_secret_value().strip():
        return None
    if len(token) > MAX_COOKIE_CHARS or token.count(".") != 1:
        return None
    payload, _, signature = token.partition(".")
    try:
        if not hmac.compare_digest(_mac(payload, settings), _unb64(signature)):
            return None
        body = json.loads(_unb64(payload))
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    key, version, name, expires = (body.get(field) for field in ("k", "v", "n", "exp"))
    if not isinstance(key, str) or not key or not isinstance(name, str):
        return None
    if type(version) is not int or type(expires) is not int:
        return None
    try:
        expires_at = datetime.fromtimestamp(expires, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    if expires_at <= timeutil.SystemClock().now():
        return None
    return OperatorClaims(login_key=key, version=version, name=name, expires_at=expires_at)


# --- the console ------------------------------------------------------------------------


def contact(record: AirlineRecord) -> AdminContact:
    """The airline's operations contact, from its verified answers."""
    airline = record.submitted().airline
    subject = quote(f"TEPHRA · {airline.name} ({airline.icao})")
    return AdminContact(
        ops_email=airline.ops_email,
        contact_name=airline.contact_name,
        mailto=f"mailto:{airline.ops_email}?subject={subject}",
    )
