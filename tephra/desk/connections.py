"""Airline data connections: a source an airline pushes aircraft positions into.

A dispatcher creates a connection on the Desk's Data connections and copies its key once; only
the key's SHA-256 is stored. A push (``tephra.positions/1``) is checked record by record: a
position must be well formed and measured within :data:`PUSH_FRESH_S` of TEPHRA's active clock,
and the ones that pass become :class:`Aircraft` beside the ADS-B targets
(``Runtime.take_push``). Nothing here plans, drafts or calls a model; the exposure check that
follows a push is the same one ADS-B gets. :func:`dry_run` checks a push file the same way for
an airline's workspace and takes nothing in.
"""

import hashlib
import secrets
from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import ValidationError

from tephra.airline.models import DryRunRecord, DryRunResult, DryRunSection
from tephra.desk import audit
from tephra.desk.crew_reports import CrewEntry
from tephra.geo.units import ft_to_fl
from tephra.models import (
    PUSH_SOURCE_PREFIX,
    Aircraft,
    AuditAction,
    Connection,
    ConnectionView,
    PositionBatch,
    PushedFlightPlan,
    PushedPosition,
    PushProblem,
    is_airline_callsign,
)
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil

__all__ = [
    "KEY_PREFIX",
    "PUSH_FRESH_S",
    "ConnectionNotFound",
    "NotAPush",
    "checked_plans",
    "checked_positions",
    "create_connection",
    "dry_run",
    "find_by_key",
    "list_connections",
    "push_source_id",
    "refusal",
    "revoke_connection",
    "save_counts",
    "view",
]

KEY_PREFIX: Final = "tph_"
PUSH_FRESH_S: Final = 300
"""A pushed position older than this (on TEPHRA's clock) is refused, and drops off the map"""
FUTURE_SLACK_S: Final = 120
TEPHRA_CLOCK: Final = "TEPHRA's clock"
WALL_CLOCK: Final = "the current time"
NOT_CHECKED_NOTE: Final = "Taken, but not checked against the ash: no airline-style callsign"
"""Exposure skips a target without an airline-style callsign (``Aircraft.airline``)."""


class ConnectionNotFound(LookupError):
    pass


class NotAPush(ValueError):
    """The file is not a push at all: no or another format, no record, a section over its cap."""


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
    return f"{PUSH_SOURCE_PREFIX}{connection.id}:{timeutil.ddhhmmz(at)}"


PATTERN_WORDS: Final[dict[str, str]] = {
    "hex": "6 characters, 0-9 and a-f",
    "callsign": "2 to 8 letters and digits, such as RFA4259",
    "type_icao": "2 to 4 letters and digits, such as A320",
    "flight": "3 to 8 letters and digits, such as RFA4259",
    "origin_icao": "a 4-letter ICAO airport code, such as WIII",
    "dest_icao": "a 4-letter ICAO airport code, such as WIII",
}
"""The pattern each field must match, in the words the onboarding pages use."""
REASONS_SHOWN: Final = 3
TIME_FIELDS: Final = frozenset({"observed_at", "std", "sta"})


def _plain(error: Any) -> str:
    """One pydantic error in an operations person's words, never a regular expression."""
    kind = str(error.get("type", ""))
    field = str(error["loc"][-1]) if error.get("loc") else ""
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "needed"
    if kind == "string_pattern_mismatch":
        return PATTERN_WORDS.get(field, "not in the expected form")
    if kind in {"greater_than_equal", "greater_than", "less_than_equal", "less_than"}:
        words = {
            "greater_than_equal": "at least",
            "greater_than": "more than",
            "less_than_equal": "at most",
            "less_than": "less than",
        }
        bound = next(iter(ctx.values()), "")
        return (
            f"must be {words[kind]} {bound:g}" if isinstance(bound, int | float) else "out of range"
        )
    if kind.startswith(("datetime", "timezone")) or field in TIME_FIELDS:
        return "a UTC time, such as 2026-09-05T10:32:00.000Z"
    if kind in {"float_parsing", "float_type"}:
        return "a number"
    if kind in {"int_parsing", "int_type", "int_from_float"}:
        return "a whole number"
    if kind in {"string_type", "string_too_short", "string_too_long"}:
        return str(error.get("msg", "not valid text")).replace("String", "text").lower()
    return str(error.get("msg", "not valid")).removeprefix("Value error, ")


def refusal(exc: ValidationError, unnamed: str = "record") -> str:
    """Every problem of a refused record (the first few, then how many more)."""
    errors = exc.errors()
    words = [
        f"{'.'.join(str(part) for part in e.get('loc', ())) or unnamed}: {_plain(e)}"
        for e in errors
    ]
    shown = "; ".join(words[:REASONS_SHOWN])
    more = len(words) - REASONS_SHOWN
    return f"{shown}; +{more} more" if more > 0 else shown


def _check_position(
    record: Any, index: int, at: datetime, *, clock_words: str = TEPHRA_CLOCK
) -> PushedPosition | PushProblem:
    """One pushed position, well formed and measured within :data:`PUSH_FRESH_S` of ``at``."""
    try:
        position = PushedPosition.model_validate(record)
    except ValidationError as exc:
        return PushProblem(index=index, reason=refusal(exc))
    oldest, newest = at - timedelta(seconds=PUSH_FRESH_S), at + timedelta(seconds=FUTURE_SLACK_S)
    if not oldest <= position.observed_at <= newest:
        return PushProblem(
            index=index,
            reason=f"observed_at {timeutil.to_iso(position.observed_at)} is not within "
            f"{PUSH_FRESH_S // 60} min of {clock_words} ({timeutil.to_iso(at)})",
        )
    return position


def _check_plan(record: Any, index: int) -> PushedFlightPlan | PushProblem:
    try:
        return PushedFlightPlan.model_validate(record)
    except ValidationError as exc:
        return PushProblem(section="flight_plans", index=index, reason=refusal(exc))


def checked_positions(
    raw: Sequence[dict[str, Any]], connection: Connection, at: datetime
) -> tuple[list[Aircraft], list[PushProblem]]:
    """The positions that pass, as aircraft, and why each other one was refused."""
    accepted: list[Aircraft] = []
    problems: list[PushProblem] = []
    source_id = push_source_id(connection, at)
    for index, record in enumerate(raw):
        position = _check_position(record, index, at)
        if isinstance(position, PushProblem):
            problems.append(position)
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
        plan = _check_plan(record, index)
        if isinstance(plan, PushProblem):
            problems.append(plan)
        else:
            plans.append(plan)
    return plans, problems


# --- the workspace's dry run ------------------------------------------------------------


def dry_run(raw: dict[str, Any], at: datetime) -> DryRunResult:
    """``raw`` checked record by record as a push would be, against ``at`` (the wall clock: an
    airline's own TEPHRA runs LIVE, where its clock is the wall clock). Pure: nothing is
    stored, published or taken in. Pilot reports are checked for shape only (the flight lookup
    needs the live picture)."""
    try:
        batch = PositionBatch.model_validate(raw)
    except ValidationError as exc:
        raise NotAPush(refusal(exc, "file")) from None
    rejected: list[PushProblem] = []
    accepted: list[DryRunRecord] = []
    for index, record in enumerate(batch.positions):
        position = _check_position(record, index, at, clock_words=WALL_CLOCK)
        if isinstance(position, PushProblem):
            rejected.append(position)
        else:
            accepted.append(_position_line(position, index))
    for index, record in enumerate(batch.flight_plans):
        plan = _check_plan(record, index)
        if isinstance(plan, PushProblem):
            rejected.append(plan)
        else:
            text = f"{plan.flight} · {plan.origin_icao} → {plan.dest_icao}"
            accepted.append(DryRunRecord(section="flight_plans", index=index, text=text))
    for index, record in enumerate(batch.pilot_reports):
        try:
            entry = CrewEntry.model_validate(record)
        except ValidationError as exc:
            reason = refusal(exc, "report")
            rejected.append(PushProblem(section="pilot_reports", index=index, reason=reason))
            continue
        text = f"{entry.callsign or entry.hex} · {entry.observed_at.strftime('%H:%MZ')}"
        accepted.append(DryRunRecord(section="pilot_reports", index=index, text=text))
    return DryRunResult(
        format=batch.format,
        checked_at=at,
        positions=_section(batch.positions, accepted, "positions"),
        flight_plans=_section(batch.flight_plans, accepted, "flight_plans"),
        pilot_reports=_section(batch.pilot_reports, accepted, "pilot_reports"),
        rejected=rejected,
        accepted=accepted,
    )


def _position_line(position: PushedPosition, index: int) -> DryRunRecord:
    text = " · ".join(
        [
            position.hex,
            position.callsign or "no callsign",
            f"{position.lat:.2f}, {position.lon:.2f}",
            f"FL{ft_to_fl(position.alt_baro_ft):03d}",
        ]
    )
    note = None if is_airline_callsign(position.callsign) else NOT_CHECKED_NOTE
    return DryRunRecord(section="positions", index=index, text=text, note=note)


def _section(raw: Sequence[Any], accepted: Sequence[DryRunRecord], name: str) -> DryRunSection:
    return DryRunSection(total=len(raw), accepted=sum(1 for r in accepted if r.section == name))
