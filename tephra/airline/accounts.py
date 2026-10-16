"""Airline accounts in the store: create, sign-in lookups, recover, update, delete, and the
Desk's verify, decline and delete.

Two collections: ``airlines`` (the record a Desk review reads: status, answers, private
history) and ``airline_logins`` (credentials, keyed by a hash of the email). Every change is a
``store.update`` whose ``change`` checks the version and raises to write nothing, so it has no
side effects (a Firestore transaction may run it twice). Nothing here writes the audit trail
or publishes an event: an airline is never part of the shared picture.
"""

import hashlib
import secrets
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from typing import Any, Final, Literal

from pydantic import ValidationError

from tephra.airline.models import (
    AirlineAnswers,
    AirlineLogin,
    AirlineRecord,
    AirlineStatus,
    AssistantChoice,
    HistoryAction,
    HistoryEntry,
)
from tephra.store.base import Collection, Store, Where
from tephra.util.hashing import sha256_json

__all__ = [
    "MAX_HISTORY",
    "MAX_PENDING",
    "MAX_STORED",
    "PUBLIC_MAIL_DOMAINS",
    "AirlineNotFound",
    "AnswersLocked",
    "EmailTaken",
    "NotDeclined",
    "NotPending",
    "VersionConflict",
    "create_account",
    "decide",
    "delete_account",
    "desk_delete",
    "end_sessions",
    "get_login",
    "get_record",
    "list_airlines",
    "login_key",
    "onboarding_full",
    "pending_count",
    "reviewer_flags",
    "set_password",
    "update_answers",
    "update_assistant",
    "verify_history",
]

MAX_HISTORY: Final = 100
MAX_PENDING: Final = 200
MAX_STORED: Final = 1000
PUBLIC_MAIL_DOMAINS: Final = frozenset(
    {"gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "icloud.com", "proton.me"}
)
GENESIS: Final = "0" * 64
_LOGIN_LABEL: Final = "tephra.airline/1|"


class EmailTaken(Exception):
    pass


class AirlineNotFound(LookupError):
    pass


class VersionConflict(Exception):
    pass


class AnswersLocked(Exception):
    def __init__(self, status: AirlineStatus) -> None:
        super().__init__(status)
        self.status = status


class NotPending(Exception):
    pass


class NotDeclined(Exception):
    pass


class _Exists(Exception):
    """An id drawn twice: ``put`` would replace the other airline silently."""


def login_key(email: str) -> str:
    return hashlib.sha256((_LOGIN_LABEL + email.strip().lower()).encode("utf-8")).hexdigest()


def _new_id() -> str:
    return "AL-" + secrets.token_hex(6)


# --- the private history ----------------------------------------------------------------


def _entry(
    history: Sequence[HistoryEntry],
    *,
    at: datetime,
    actor: str,
    action: HistoryAction,
    note: str | None = None,
) -> HistoryEntry:
    prev = history[-1].sha256 if history else GENESIS
    body: dict[str, Any] = {
        "seq": len(history) + 1,
        "at": at,
        "actor": actor,
        "action": action,
        "note": note,
        "prev_sha256": prev,
    }
    unsigned = HistoryEntry(**body, sha256=GENESIS).model_dump(mode="json", exclude={"sha256"})
    return HistoryEntry(**body, sha256=sha256_json(unsigned))


_OWN_CHANGES: Final = frozenset({"answers_changed", "assistant_changed"})


def _with_own_change(
    history: Sequence[HistoryEntry], *, at: datetime, action: HistoryAction
) -> list[HistoryEntry]:
    """The history with one more airline change. A change of the same kind as the last entry,
    or any change once the history holds ``MAX_HISTORY`` entries, takes the last entry's place
    (the last entry has no successor, so the chain still checks out): edits never grow a record
    toward the store's document limit."""
    last = history[-1] if history else None
    folds = (
        last is not None
        and last.actor == "airline"
        and last.action in _OWN_CHANGES
        and (last.action == action or len(history) >= MAX_HISTORY)
    )
    kept = list(history[:-1]) if folds else list(history)
    return [*kept, _entry(kept, at=at, actor="airline", action=action)]


def verify_history(entries: Sequence[HistoryEntry]) -> int | None:
    """The first ``seq`` whose link or hash does not check out, or None. A chain the writer
    can rewrite shows accidents, not tampering, so nothing calls it intact."""
    prev = GENESIS
    for entry in entries:
        unsigned = entry.model_dump(mode="json", exclude={"sha256"})
        if entry.prev_sha256 != prev or sha256_json(unsigned) != entry.sha256:
            return entry.seq
        prev = entry.sha256
    return None


# --- reviewer flags ---------------------------------------------------------------------


def _domain(email: str) -> str:
    return email.rpartition("@")[2].lower()


def reviewer_flags(
    answers: AirlineAnswers, email: str, *, airports: Iterable[str], designators: Iterable[str]
) -> list[str]:
    """Hints for the dispatcher who verifies; never shown to the airline, never blocking."""
    airline = answers.airline
    held = set(designators)
    codes = dict.fromkeys([airline.icao, airline.callsign_prefix, *answers.fleet.extra_prefixes])
    flags = [
        f"designator {code} appears in TEPHRA's route table: a real operator may hold it; "
        "verify by a person"
        for code in codes
        if code in held
    ]
    domains = {_domain(airline.ops_email), _domain(email)}
    if domains & PUBLIC_MAIL_DOMAINS:
        flags.append("contact email domain is a public mail provider")
    if len(domains) > 1:
        flags.append("account email domain differs from the operations email's")
    known = set(airports)
    outside = [a.icao for a in answers.network.airports if a.icao not in known]
    if outside:
        flags.append(f"airports outside TEPHRA's airport list: {', '.join(outside)}")
    if airline.aoc_number is None:
        flags.append("no AOC number given")
    return flags


# --- reads ------------------------------------------------------------------------------


async def get_record(store: Store, airline_id: str) -> AirlineRecord:
    doc = await store.get(Collection.AIRLINES, airline_id)
    if doc is None:
        raise AirlineNotFound(airline_id)
    return AirlineRecord.model_validate(doc)


async def get_login(store: Store, key: str) -> AirlineLogin | None:
    doc = await store.get(Collection.AIRLINE_LOGINS, key)
    return None if doc is None else AirlineLogin.model_validate(doc)


async def onboarding_full(store: Store) -> bool:
    """200 airlines pending, or 1,000 stored (one login each). Counted by the store, so no
    record is read."""
    if await pending_count(store) >= MAX_PENDING:
        return True
    return await store.count(Collection.AIRLINE_LOGINS) >= MAX_STORED


async def pending_count(store: Store) -> int:
    return await store.count(Collection.AIRLINES, [Where("status", "==", "pending")])


async def list_airlines(
    store: Store, status: AirlineStatus | Literal["all"], limit: int
) -> list[AirlineRecord]:
    """Newest ``submitted_at`` first."""
    where = [] if status == "all" else [Where("status", "==", status)]
    docs = await store.query(
        Collection.AIRLINES, where, order_by="submitted_at", descending=True, limit=limit
    )
    records: list[AirlineRecord] = []
    for doc in docs:
        try:
            records.append(AirlineRecord.model_validate(doc))
        except ValidationError:
            continue
    return records


# --- the airline's own changes ----------------------------------------------------------


async def create_account(
    store: Store,
    *,
    answers: AirlineAnswers,
    email: str,
    password_hash: str,
    recovery_sha256: str,
    flags: list[str],
    at: datetime,
) -> tuple[AirlineRecord, AirlineLogin]:
    """The record first, then the login: a lost race on the email deletes the record just
    written (login first could leave a login with no record, the email taken for good)."""
    key = login_key(email)
    record = await _write_new_record(store, answers, email, key, flags, at)
    login = AirlineLogin(
        login_key=key,
        airline_id=record.id,
        email=email,
        password=password_hash,
        recovery_sha256=recovery_sha256,
        session_version=1,
        created_at=at,
        password_changed_at=at,
    )

    def claim(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is not None:
            raise EmailTaken()
        return login.model_dump(mode="json")

    try:
        await store.update(Collection.AIRLINE_LOGINS, key, claim)
    except EmailTaken:
        await store.delete(Collection.AIRLINES, record.id)
        raise
    return record, login


async def _write_new_record(
    store: Store,
    answers: AirlineAnswers,
    email: str,
    key: str,
    flags: list[str],
    at: datetime,
) -> AirlineRecord:
    """A new record under a new id; an id drawn twice retries once with another."""

    def fresh() -> AirlineRecord:
        return AirlineRecord(
            id=_new_id(),
            version=1,
            status="pending",
            login_key=key,
            email=email,
            answers=answers,
            submitted_at=at,
            updated_at=at,
            flags=flags,
            history=[_entry([], at=at, actor="airline", action="created")],
        )

    try:
        return await _put_new(store, fresh())
    except _Exists:
        return await _put_new(store, fresh())


async def _put_new(store: Store, record: AirlineRecord) -> AirlineRecord:
    doc = record.model_dump(mode="json")

    def create(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is not None:
            raise _Exists()
        return doc

    await store.update(Collection.AIRLINES, record.id, create)
    return record


def _changing(
    version: int, edit: Callable[[AirlineRecord], AirlineRecord]
) -> Callable[[dict[str, Any] | None], dict[str, Any]]:
    """A ``store.update`` change: refuse a missing record or another version, else ``edit``
    it and bump the version."""

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise AirlineNotFound()
        record = AirlineRecord.model_validate(stored)
        if record.version != version:
            raise VersionConflict()
        edited = edit(record)
        return edited.model_copy(update={"version": record.version + 1}).model_dump(mode="json")

    return change


async def _apply(
    store: Store, airline_id: str, version: int, edit: Callable[[AirlineRecord], AirlineRecord]
) -> AirlineRecord:
    written = await store.update(Collection.AIRLINES, airline_id, _changing(version, edit))
    return AirlineRecord.model_validate(written)


async def update_answers(
    store: Store,
    airline_id: str,
    *,
    version: int,
    answers: AirlineAnswers,
    flags: list[str],
    at: datetime,
) -> AirlineRecord:
    """Answers change only while the airline is pending verification."""

    def edit(record: AirlineRecord) -> AirlineRecord:
        if record.status != "pending":
            raise AnswersLocked(record.status)
        history = _with_own_change(record.history, at=at, action="answers_changed")
        return record.model_copy(
            update={"answers": answers, "updated_at": at, "flags": flags, "history": history}
        )

    return await _apply(store, airline_id, version, edit)


async def update_assistant(
    store: Store, airline_id: str, *, version: int, assistant: AssistantChoice, at: datetime
) -> AirlineRecord:
    """The model choice may change in every status: it goes only into the airline's kit."""

    def edit(record: AirlineRecord) -> AirlineRecord:
        history = _with_own_change(record.history, at=at, action="assistant_changed")
        answers = record.answers.model_copy(update={"assistant": assistant})
        return record.model_copy(update={"answers": answers, "updated_at": at, "history": history})

    return await _apply(store, airline_id, version, edit)


async def set_password(
    store: Store,
    key: str,
    *,
    password_hash: str,
    recovery_sha256: str,
    expected_recovery_sha256: str,
    at: datetime,
) -> AirlineLogin:
    """A recovery: the new password and code, and a new session version (every other
    browser is signed out). The code checked must still be the stored one."""

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise AirlineNotFound()
        login = AirlineLogin.model_validate(stored)
        if login.recovery_sha256 != expected_recovery_sha256:
            raise VersionConflict()
        return login.model_copy(
            update={
                "password": password_hash,
                "recovery_sha256": recovery_sha256,
                "session_version": login.session_version + 1,
                "password_changed_at": at,
            }
        ).model_dump(mode="json")

    return AirlineLogin.model_validate(await store.update(Collection.AIRLINE_LOGINS, key, change))


async def end_sessions(store: Store, key: str, *, version: int) -> None:
    """Sign-out: a new session version, so the signed-out cookie (and every other browser's,
    since all share the version) no longer opens the workspace. A cookie already out of date
    changes nothing."""

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise AirlineNotFound()
        login = AirlineLogin.model_validate(stored)
        if login.session_version != version:
            raise VersionConflict()
        return login.model_copy(update={"session_version": version + 1}).model_dump(mode="json")

    try:
        await store.update(Collection.AIRLINE_LOGINS, key, change)
    except (AirlineNotFound, VersionConflict):
        return


async def delete_account(store: Store, record: AirlineRecord) -> None:
    """Both documents; the login goes first, so no cookie verifies once this starts."""
    await store.delete(Collection.AIRLINE_LOGINS, record.login_key)
    await store.delete(Collection.AIRLINES, record.id)


# --- the Desk ---------------------------------------------------------------------------


async def decide(
    store: Store,
    airline_id: str,
    *,
    version: int,
    actor: str,
    verified: bool,
    note: str | None,
    at: datetime,
) -> AirlineRecord:
    """Verify or decline a pending airline: its own history records who and why. No audit
    entry and no event: the public audit would list airlines publicly."""
    status: AirlineStatus = "verified" if verified else "declined"

    def edit(record: AirlineRecord) -> AirlineRecord:
        if record.status != "pending":
            raise NotPending()
        entry = _entry(record.history, at=at, actor=actor, action=status, note=note)
        return record.model_copy(
            update={
                "status": status,
                "decided_at": at,
                "decline_reason": None if verified else note,
                "updated_at": at,
                "history": [*record.history, entry],
            }
        )

    return await _apply(store, airline_id, version, edit)


async def desk_delete(store: Store, airline_id: str, *, version: int) -> AirlineRecord:
    """A declined airline's record and login (spam must not fill the 1,000-record cap)."""
    record = await get_record(store, airline_id)
    if record.version != version:
        raise VersionConflict()
    if record.status != "declined":
        raise NotDeclined()
    await delete_account(store, record)
    return record
