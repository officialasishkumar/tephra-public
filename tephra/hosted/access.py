"""Who may act inside an airline, and which operators are signed in, held for 10 minutes.

Every request under ``/a/<ICAO>/`` and every operator request would otherwise read the login
and the member (or the operator) from the store. Entries, found or not found, live
:data:`TTL_S`; every member, operator and session function calls :meth:`AccessCache.drop`, so a
removal, a role change, a sign-out everywhere or a password change takes effect on the next
request here. Another instance (a rollout overlap) sees such a change within 10 minutes at
most. ``generation`` moves on every drop: open event streams compare it every 15 s.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from tephra.airline.models import AirlineLogin
from tephra.hosted.models import Member, Operator, TenantRecord
from tephra.store.base import Collection, Store

__all__ = ["TTL_S", "AccessCache", "effective", "member_doc_id"]

TTL_S: Final = 600.0


def member_doc_id(icao: str, login_key: str) -> str:
    return f"{icao}~{login_key}"


def effective(member: Member, record: TenantRecord) -> Member:
    """``TenantRecord.ops_managers`` decides who is an ops manager (S14)."""
    if member.id in record.ops_managers and member.role != "ops_manager":
        return member.model_copy(update={"role": "ops_manager"})
    if member.id not in record.ops_managers and member.role == "ops_manager":
        return member.model_copy(update={"role": "dispatcher"})
    return member


@dataclass(frozen=True, slots=True)
class _Held:
    at: float
    version: int | None
    """The login's (or operator's) session version; None when it does not exist"""
    found: Member | Operator | None


class AccessCache:
    """One per app. Keys are ``("member", login_key, icao)`` and ``("operator", login_key)``."""

    def __init__(self, *, ttl_s: float = TTL_S, clock: Callable[[], float] = time.monotonic):
        self._ttl_s = ttl_s
        self._clock = clock
        self._held: dict[tuple[str, ...], _Held] = {}
        self.generation = 0

    def holds_member(self, login_key: str, icao: str) -> bool:
        """Whether the next :meth:`member` lookup is answered without a store read (the
        airline request throttles count only a miss)."""
        return self._fresh(("member", login_key, icao)) is not None

    async def member(
        self,
        store: Store,
        login_key: str,
        version: int,
        icao: str,
        *,
        record: TenantRecord | None = None,
    ) -> Member | None:
        """The member signed in with this login and cookie version, or None. With ``record``
        the role follows ``record.ops_managers``."""
        key = ("member", login_key, icao)
        held = self._fresh(key)
        if held is None:
            generation = self.generation
            login_version = await _login_version(store, login_key)
            found = None
            if login_version is not None:
                doc = await store.get(Collection.HOSTED_MEMBERS, member_doc_id(icao, login_key))
                found = _parse(Member, doc)
            held = _Held(self._clock(), login_version, found)
            if generation == self.generation:
                self._held[key] = held
        if held.version != version or not isinstance(held.found, Member):
            return None
        return held.found if record is None else effective(held.found, record)

    async def operator(self, store: Store, login_key: str, version: int) -> Operator | None:
        """The operator signed in with this cookie version, or None (disabled, signed out
        everywhere, removed)."""
        key = ("operator", login_key)
        held = self._fresh(key)
        if held is None:
            generation = self.generation
            found = _parse(Operator, await store.get(Collection.OPERATORS, login_key))
            held = _Held(self._clock(), None if found is None else found.session_version, found)
            if generation == self.generation:
                self._held[key] = held
        operator = held.found
        if not isinstance(operator, Operator) or held.version != version:
            return None
        return None if operator.disabled is not None else operator

    def drop(self, *, login_key: str | None = None, icao: str | None = None) -> None:
        """Forget what concerns ``login_key`` and/or ``icao`` (everything when neither)."""
        for key in list(self._held):
            if login_key is not None and key[1] != login_key:
                continue
            if icao is not None and (key[0] != "member" or key[2] != icao):
                continue
            del self._held[key]
        self.generation += 1

    def _fresh(self, key: tuple[str, ...]) -> _Held | None:
        held = self._held.get(key)
        if held is None:
            return None
        if self._clock() - held.at > self._ttl_s:
            del self._held[key]
            return None
        return held


async def _login_version(store: Store, login_key: str) -> int | None:
    login = _parse(AirlineLogin, await store.get(Collection.AIRLINE_LOGINS, login_key))
    return None if login is None else login.session_version


def _parse[T: Member | Operator | AirlineLogin](model: type[T], doc: object) -> T | None:
    if doc is None:
        return None
    try:
        return model.model_validate(doc)
    except ValidationError:
        return None
