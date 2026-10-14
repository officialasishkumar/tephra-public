"""Airline data connections: a source an airline pushes aircraft positions into.

A dispatcher creates a connection on the Connect page and copies its key once; only the key's
SHA-256 is stored. A push (``tephra.positions/1``) is checked record by record: a position must
be well formed and measured within :data:`PUSH_FRESH_S` of TEPHRA's active clock, and the ones
that pass become :class:`Aircraft` beside the ADS-B targets (``Runtime.take_push``). Nothing here
plans, drafts or calls a model; the exposure check that follows a push is the same one ADS-B
gets.
"""

import hashlib
import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import ValidationError

from tephra.desk import audit
from tephra.models import (
    Aircraft,
    AuditAction,
    Connection,
    ConnectionView,
    PushedFlightPlan,
    PushedPosition,
    PushProblem,
)
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil

__all__ = [
    "KEY_PREFIX",
    "PUSH_FRESH_S",
    "ConnectionNotFound",
    "checked_plans",
    "checked_positions",
    "create_connection",
    "find_by_key",
    "list_connections",
    "push_source_id",
    "revoke_connection",
    "save_counts",
    "view",
]

KEY_PREFIX: Final = "tph_"
PUSH_FRESH_S: Final = 300
"""A pushed position older than this (on TEPHRA's clock) is refused, and drops off the map"""
FUTURE_SLACK_S: Final = 120


class ConnectionNotFound(LookupError):
    pass


def _sha(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def view(connection: Connection, key: str | None = None) -> ConnectionView:
    return ConnectionView(**connection.model_dump(exclude={"key_sha256"}), key=key)


async def create_connection(
    store: Store, name: str, *, actor: str, sample: bool = False
) -> tuple[Connection, str]:
    """A new connection and its key, which is returned once and never stored."""
    key = KEY_PREFIX + secrets.token_urlsafe(24)
    connection = Connection(
        id=f"CN-{secrets.token_hex(5)}",
        name=name.strip(),
        sample=sample,
        created_at=timeutil.now(),
        created_by=actor,
        key_sha256=_sha(key),
        key_hint=key[-4:],
    )
    await store.put(Collection.CONNECTIONS, connection.id, connection.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.CONNECTION_CREATED,
        after={"connection_id": connection.id, "name": connection.name, "sample": sample},
    )
    return connection, key


async def list_connections(store: Store) -> list[Connection]:
    docs = await store.list_docs(Collection.CONNECTIONS, limit=100, order_by="created_at")
    return [Connection.model_validate(doc) for doc in docs]


async def find_by_key(store: Store, key: str) -> Connection | None:
    """The live connection the key belongs to; None for an unknown or revoked key."""
    if not key.startswith(KEY_PREFIX):
        return None
    docs = await store.query(
        Collection.CONNECTIONS, [Where("key_sha256", "==", _sha(key))], limit=1
    )
    if not docs:
        return None
    connection = Connection.model_validate(docs[0])
    return None if connection.revoked_at is not None else connection


async def revoke_connection(store: Store, connection_id: str, *, actor: str) -> Connection:
    doc = await store.get(Collection.CONNECTIONS, connection_id)
    if doc is None:
        raise ConnectionNotFound(connection_id)
    connection = Connection.model_validate(doc)
    if connection.revoked_at is None:
        connection = connection.model_copy(update={"revoked_at": timeutil.now()})
        await store.put(Collection.CONNECTIONS, connection.id, connection.model_dump(mode="json"))
        await audit.record(
            store,
            actor=actor,
            action=AuditAction.CONNECTION_REVOKED,
            before={"connection_id": connection.id, "name": connection.name},
        )
    return connection


async def save_counts(
    store: Store, connection: Connection, *, accepted: int, rejected: int, at: datetime
) -> Connection:
    """The connection's counters after a push (read again: two pushes may overlap)."""
    doc = await store.get(Collection.CONNECTIONS, connection.id)
    current = Connection.model_validate(doc) if doc is not None else connection
    updated = current.model_copy(
        update={
            "last_push_at": at,
            "pushes": current.pushes + 1,
            "accepted": current.accepted + accepted,
            "rejected": current.rejected + rejected,
        }
    )
    await store.put(Collection.CONNECTIONS, updated.id, updated.model_dump(mode="json"))
    return updated


def push_source_id(connection: Connection, at: datetime) -> str:
    return f"PUSH:{connection.id}:{timeutil.ddhhmmz(at)}"


def _reason(exc: ValidationError) -> str:
    first = exc.errors()[0]
    where = ".".join(str(part) for part in first.get("loc", ())) or "record"
    return f"{where}: {first.get('msg', 'invalid')}"


def checked_positions(
    raw: Sequence[dict[str, Any]], connection: Connection, at: datetime
) -> tuple[list[Aircraft], list[PushProblem]]:
    """The positions that pass, as aircraft, and why each other one was refused."""
    accepted: list[Aircraft] = []
    problems: list[PushProblem] = []
    oldest, newest = at - timedelta(seconds=PUSH_FRESH_S), at + timedelta(seconds=FUTURE_SLACK_S)
    source_id = push_source_id(connection, at)
    for index, record in enumerate(raw):
        try:
            position = PushedPosition.model_validate(record)
        except ValidationError as exc:
            problems.append(PushProblem(index=index, reason=_reason(exc)))
            continue
        if not oldest <= position.observed_at <= newest:
            problems.append(
                PushProblem(
                    index=index,
                    reason=f"observed_at {timeutil.to_iso(position.observed_at)} is not within "
                    f"{PUSH_FRESH_S // 60} min of TEPHRA's clock ({timeutil.to_iso(at)})",
                )
            )
            continue
        accepted.append(
            Aircraft(
                hex=position.hex,
                callsign=position.callsign,
                type_icao=position.type_icao,
                lat=position.lat,
                lon=position.lon,
                alt_baro_ft=position.alt_baro_ft,
                gs_kt=position.gs_kt,
                track_deg=position.track_deg,
                observed_at=position.observed_at,
                source_id=source_id,
            )
        )
    return accepted, problems


def checked_plans(
    raw: Sequence[dict[str, Any]],
) -> tuple[list[PushedFlightPlan], list[PushProblem]]:
    """The flight plans that pass, and why each other one was refused."""
    plans: list[PushedFlightPlan] = []
    problems: list[PushProblem] = []
    for index, record in enumerate(raw):
        try:
            plans.append(PushedFlightPlan.model_validate(record))
        except ValidationError as exc:
            problems.append(PushProblem(section="flight_plans", index=index, reason=_reason(exc)))
    return plans, problems
