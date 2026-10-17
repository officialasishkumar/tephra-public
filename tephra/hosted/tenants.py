"""A hosted airline's record and its states (SPEC §3.4):

``setup`` → ``shadow`` ⇄ ``live``; shadow or live → ``setup`` (the ops manager stops runs);
setup, shadow or live → ``suspended`` (an operator); suspended → ``shadow`` (resume, never
straight to LIVE) or, 7 days after the suspension, → ``deleting`` → ``deleted`` (a tombstone).

Every change is a compare-and-set on ``hosted_tenants/<ICAO>`` whose change function checks the
state, so two people acting at once never both win. Shadow and live hold one of the site's
places (``hosted_slots/site``, also compare-and-set). Each transition writes an entry into the
airline's own audit chain, on its store, inside its space's binding (wall clock); entries name
people by display name and member id, never by email.
"""

import hashlib
from collections.abc import Callable, Sequence
from collections.abc import Collection as Many
from datetime import date, datetime, timedelta
from typing import Any, Final

from pydantic import ValidationError

from tephra.agents.quota import quota_day
from tephra.airline.models import AirlineAnswers, AirlineLogin, AirlineRecord, PolicyChange
from tephra.config import RegionKey, Settings
from tephra.desk import audit
from tephra.feeds.airports import AirportCatalogue
from tephra.hosted import policy as hosted_policy
from tephra.hosted.access import effective, member_doc_id
from tephra.hosted.golive import derive_region
from tephra.hosted.models import (
    RUNNING,
    CanSetUp,
    ChainLine,
    HostedMe,
    HostedRefused,
    LiveLine,
    Member,
    Membership,
    PausedLine,
    PolicyConfirmed,
    PolicyLine,
    PolicyVersion,
    RecordHead,
    RecordTab,
    RuntimeLine,
    SealedKey,
    SlotDoc,
    Space,
    SraAcceptance,
    Stamp,
    SuspendedLine,
    TenantAssistant,
    TenantHeader,
    TenantRecord,
    TenantState,
    You,
)
from tephra.hosted.settings_for import check_assistant, hosted_models
from tephra.models import AuditAction, AuditEntry, ChainHead, OperatorPolicy
from tephra.store.base import Collection, Store, Where

__all__ = [
    "DELETE_AFTER",
    "MAX_RESTARTS",
    "RECORD_PAGE",
    "SLOTS_ID",
    "actor_of",
    "back_to_shadow",
    "confirm_policy",
    "display_name",
    "finish_delete",
    "get_tenant",
    "go_live",
    "header",
    "hosted_me",
    "list_tenants",
    "mark_deleting",
    "member_by",
    "member_id",
    "note_chain_checked",
    "note_restart",
    "record_page",
    "record_sra",
    "record_tab",
    "release_slot",
    "resume",
    "set_assistant",
    "set_key",
    "set_policy_version",
    "set_up",
    "shown_by",
    "slots",
    "start",
    "stop_runs",
    "suspend",
    "withdraw_sra",
    "wrong_state",
]

DELETE_AFTER: Final = timedelta(days=7)
"""An operator may delete a suspended airline's data this long after the suspension (S11)."""
MAX_RESTARTS: Final = 6
SLOTS_ID: Final = "site"
RECORD_PAGE: Final = 50
UPDATING_WITHIN: Final = timedelta(seconds=150)
_NAME_PUNCTUATION: Final = frozenset(" .'-_")
_CHANGEABLE: Final[frozenset[TenantState]] = frozenset({"setup", "shadow", "live"})


# --- names and actors -------------------------------------------------------------------


def display_name(raw: str) -> str:
    """The Desk's name rule: 2 to 32 letters, digits, spaces or . ' - _ (no email ever)."""
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 32 or not all(ch.isalnum() or ch in _NAME_PUNCTUATION for ch in name):
        raise HostedRefused(
            422, "display_name", "A display name is 2 to 32 letters, digits, spaces or . ' - _"
        )
    return name


def member_id(icao: str, login_key: str) -> str:
    return "MB-" + hashlib.sha256(member_doc_id(icao, login_key).encode()).hexdigest()[:10]


def member_by(member: Member) -> str:
    return f"{member.display_name}#{member.id}"


def shown_by(by: str) -> str:
    """A stamp's ``by`` as pages show it: the member's name, or "TEPHRA's operators" for an
    operator (a resume restarts the runs in the operator's name)."""
    return "TEPHRA's operators" if by.startswith("operator:") else by.split("#")[0]


def actor_of(by: str) -> str:
    """The audit actor for a stamp: ``operator:<name>#<k8>`` as it is, a member as
    ``desk:<name>#<member id>``."""
    return by if by.startswith("operator:") else f"desk:{by}"


async def _note(
    space: Space,
    *,
    by: str,
    action: AuditAction,
    note: str | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEntry:
    with space.bound():
        return await audit.record(
            space.store, actor=actor_of(by), action=action, note=note, after=after
        )


# --- reads ------------------------------------------------------------------------------


async def get_tenant(store: Store, icao: str) -> TenantRecord | None:
    doc = await store.get(Collection.HOSTED_TENANTS, icao)
    return None if doc is None else TenantRecord.model_validate(doc)


async def list_tenants(store: Store, states: Many[TenantState] | None = None) -> list[TenantRecord]:
    where = [] if states is None else [Where("state", "in", sorted(states))]
    docs = await store.query(Collection.HOSTED_TENANTS, where, limit=1000)
    records: list[TenantRecord] = []
    for doc in docs:
        try:
            records.append(TenantRecord.model_validate(doc))
        except ValidationError:
            continue
    return sorted(records, key=lambda record: record.icao)


async def slots(store: Store) -> SlotDoc:
    doc = await store.get(Collection.HOSTED_SLOTS, SLOTS_ID)
    return SlotDoc() if doc is None else SlotDoc.model_validate(doc)


# --- compare-and-set helpers ------------------------------------------------------------


def _missing() -> HostedRefused:
    return HostedRefused(404, "no_such_airline", "No such airline on this site")


def wrong_state(record: TenantRecord) -> HostedRefused:
    return HostedRefused(409, "wrong_state", f"{record.name} is {record.state} now")


async def _change(
    store: Store, icao: str, edit: Callable[[TenantRecord], TenantRecord]
) -> TenantRecord:
    """``edit`` runs inside the store's transaction (perhaps twice): it checks and raises."""

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise _missing()
        record = TenantRecord.model_validate(stored)
        edited = edit(record)
        return edited.model_copy(update={"version": record.version + 1}).model_dump(mode="json")

    return TenantRecord.model_validate(await store.update(Collection.HOSTED_TENANTS, icao, change))


def _moved(record: TenantRecord, state: TenantState, at: datetime, **update: Any) -> TenantRecord:
    return record.model_copy(update={"state": state, "state_since": at, **update})


async def _claim_slot(store: Store, icao: str, max_slots: int) -> bool:
    """A place for ``icao``; True when this call took it (False: it already held one)."""
    took = False

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal took
        held = SlotDoc() if stored is None else SlotDoc.model_validate(stored)
        if icao in held.holders:
            took = False
            return held.model_dump(mode="json")
        if len(held.holders) >= max_slots:
            raise HostedRefused(
                409, "airline_limit_reached", "All airline places on this site are in use"
            )
        took = True
        return SlotDoc(holders=[*held.holders, icao], version=held.version + 1).model_dump(
            mode="json"
        )

    await store.update(Collection.HOSTED_SLOTS, SLOTS_ID, change)
    return took


async def release_slot(store: Store, icao: str) -> None:
    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        held = SlotDoc() if stored is None else SlotDoc.model_validate(stored)
        holders = [holder for holder in held.holders if holder != icao]
        version = held.version + (1 if holders != held.holders else 0)
        return SlotDoc(holders=holders, version=version).model_dump(mode="json")

    await store.update(Collection.HOSTED_SLOTS, SLOTS_ID, change)


# --- transitions ------------------------------------------------------------------------


async def set_up(
    store: Store,
    record: AirlineRecord,
    login: AirlineLogin,
    name: str,
    *,
    space: Space,
    settings: Settings,
    base_policy: OperatorPolicy,
    airports: AirportCatalogue,
    at: datetime,
) -> tuple[TenantRecord, Member]:
    """(none) → setup, by the account holder of a verified airline an operator approved for
    hosting. The holder becomes the first ops manager; the onboarding policy changes become
    policy version 1; the assistant is taken from the answers when it names two free-tier
    models; the region is derived from the network when it can be."""
    if record.status != "verified" or record.answers is None:
        raise HostedRefused(409, "not_verified", "Only a verified airline can be hosted")
    if record.hosting is None:
        raise HostedRefused(
            409,
            "hosting_not_approved",
            "TEPHRA's operators approve hosting after verification",
        )
    if login.airline_id != record.id:
        raise HostedRefused(403, "not_record_holder", "Only the airline's own account sets up")
    answers = record.answers
    airline = answers.airline
    icao = airline.icao
    shown = display_name(name)
    stamp = Stamp(by=f"{shown}#{member_id(icao, login.login_key)}", at=at)
    member = Member(
        id=member_id(icao, login.login_key),
        icao=icao,
        login_key=login.login_key,
        email=login.email,
        display_name=shown,
        role="ops_manager",
        joined_at=at,
        invited_by=None,
    )
    tenant = TenantRecord(
        icao=icao,
        airline_id=record.id,
        name=airline.name,
        iata=airline.iata,
        version=1,
        state="setup",
        state_since=at,
        region=derive_region(answers, airports),
        created=stamp,
        ops_managers=[member.id],
        assistant=_assistant_from(answers, settings),
        policy_version=1,
    )

    def create(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is not None:
            held = TenantRecord.model_validate(stored)
            if held.state != "deleted":
                if held.airline_id == record.id:
                    raise HostedRefused(
                        409, "already_set_up", f"TEPHRA is already set up for {held.name}"
                    )
                raise HostedRefused(
                    409, "icao_taken", "Another airline uses this ICAO code on this site"
                )
        return tenant.model_dump(mode="json")

    await store.update(Collection.HOSTED_TENANTS, icao, create)
    await store.put(
        Collection.HOSTED_MEMBERS,
        member_doc_id(icao, login.login_key),
        member.model_dump(mode="json"),
    )
    with space.bound():
        await hosted_policy.put_version(
            space.store,
            PolicyVersion(
                version=1,
                base_policy_id=base_policy.policy_id,
                base_version=base_policy.version,
                changes=answers.policy.changes,
                created=stamp,
                note="From onboarding",
            ),
        )
    await _note(space, by=stamp.by, action=AuditAction.HOSTED_SETUP, after={"state": "setup"})
    return tenant, member


def _assistant_from(answers: AirlineAnswers, settings: Settings) -> TenantAssistant | None:
    choice = answers.assistant
    table = hosted_models(settings)
    model, lite = choice.model, choice.model_lite
    if choice.provider != "gemini" or model not in table or lite not in table:
        return None
    return TenantAssistant(model=model, model_lite=lite)


async def start(
    store: Store,
    icao: str,
    *,
    region: RegionKey,
    by: str,
    max_slots: int,
    space: Space,
    at: datetime,
) -> TenantRecord:
    """setup → shadow. The checklist and the memory guard are the caller's (golive,
    registry); the place is taken here, and given back if the state moved meanwhile."""
    current = await get_tenant(store, icao)
    if current is None:
        raise _missing()
    if current.state != "setup":
        raise wrong_state(current)
    took = await _claim_slot(store, icao, max_slots)

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "setup":
            raise wrong_state(record)
        return _moved(record, "shadow", at, region=region, started=Stamp(by=by, at=at), live=None)

    try:
        updated = await _change(store, icao, edit)
    except BaseException:
        if took:
            await release_slot(store, icao)
        raise
    await _note(
        space,
        by=by,
        action=AuditAction.HOSTED_SHADOW,
        note="Started shadow runs",
        after={"state": "shadow", "region": region},
    )
    return updated


async def go_live(store: Store, icao: str, *, by: str, space: Space, at: datetime) -> TenantRecord:
    """shadow → live, recorded with the name and the time (the caller checks the typed ICAO
    and the attestation)."""

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "shadow":
            raise wrong_state(record)
        return _moved(record, "live", at, live=Stamp(by=by, at=at))

    updated = await _change(store, icao, edit)
    await _note(space, by=by, action=AuditAction.HOSTED_LIVE, after={"state": "live"})
    return updated


async def back_to_shadow(
    store: Store, icao: str, *, by: str, reason: str, space: Space, at: datetime
) -> TenantRecord:
    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "live":
            raise wrong_state(record)
        return _moved(record, "shadow", at, live=None)

    updated = await _change(store, icao, edit)
    await _note(
        space, by=by, action=AuditAction.HOSTED_SHADOW, note=reason, after={"state": "shadow"}
    )
    return updated


async def stop_runs(
    store: Store, icao: str, *, by: str, reason: str, space: Space, at: datetime
) -> TenantRecord:
    """shadow or live → setup by an ops manager (D27): the place is freed."""

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state not in RUNNING:
            raise wrong_state(record)
        return _moved(record, "setup", at, live=None)

    updated = await _change(store, icao, edit)
    await release_slot(store, icao)
    await _note(
        space, by=by, action=AuditAction.HOSTED_STOPPED, note=reason, after={"state": "setup"}
    )
    return updated


async def suspend(
    store: Store, icao: str, *, by: str, reason: str, space: Space, at: datetime
) -> TenantRecord:
    """setup, shadow or live → suspended, by an operator: runs stop, pushes are refused and
    every page turns read-only. From 7 days later an operator may delete the data
    (:func:`mark_deleting`); nothing deletes it on its own."""

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state not in _CHANGEABLE:
            raise wrong_state(record)
        return _moved(
            record,
            "suspended",
            at,
            live=None,
            suspended=Stamp(by=by, at=at),
            suspend_reason=reason,
        )

    updated = await _change(store, icao, edit)
    await release_slot(store, icao)
    delete_on = (at + DELETE_AFTER).date()
    await _note(
        space,
        by=by,
        action=AuditAction.HOSTED_SUSPENDED,
        note=f"{reason} Its data can be deleted from {delete_on:%d %b %Y}.",
        after={"state": "suspended"},
    )
    return updated


async def resume(
    store: Store, icao: str, *, by: str, max_slots: int, space: Space, at: datetime
) -> TenantRecord:
    """suspended → shadow (never straight to LIVE), when a place is free."""
    current = await get_tenant(store, icao)
    if current is None:
        raise _missing()
    if current.state != "suspended":
        raise wrong_state(current)
    if current.region is None:
        raise HostedRefused(409, "wrong_state", f"{current.name} never started; set it up again")
    took = await _claim_slot(store, icao, max_slots)

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "suspended":
            raise wrong_state(record)
        return _moved(
            record,
            "shadow",
            at,
            suspended=None,
            suspend_reason=None,
            started=Stamp(by=by, at=at),
        )

    try:
        updated = await _change(store, icao, edit)
    except BaseException:
        if took:
            await release_slot(store, icao)
        raise
    await _note(space, by=by, action=AuditAction.HOSTED_RESUMED, after={"state": "shadow"})
    return updated


async def mark_deleting(store: Store, icao: str, *, by: str, at: datetime) -> TenantRecord:
    """suspended → deleting, at least :data:`DELETE_AFTER` after the suspension. The key and
    the assistant go at once; the registry purges the airline's documents in the background.
    No audit entry: the chain goes with the rest (the tombstone and a log line record it)."""

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "suspended" or record.suspended is None:
            raise wrong_state(record)
        allowed = record.suspended.at + DELETE_AFTER
        if at < allowed:
            raise HostedRefused(
                409, "too_soon", f"{record.name}'s data can be deleted from {allowed:%d %b %Y}"
            )
        return _moved(
            record, "deleting", at, model_key=None, assistant=None, deleted=Stamp(by=by, at=at)
        )

    return await _change(store, icao, edit)


TOMBSTONE_BY: Final = "deleted"
"""``created.by`` of a tombstone: who set the airline up is not kept."""


async def finish_delete(store: Store, icao: str, *, at: datetime) -> TenantRecord:
    """deleting → deleted: the tombstone keeps the code, the airline's name and the times
    (set up, deleted) and the deletion stamp; nothing about its people (no names, member ids
    or SRA signatory), no suspension reason, key, assistant or region."""

    def edit(record: TenantRecord) -> TenantRecord:
        if record.state != "deleting":
            raise wrong_state(record)
        return _moved(
            record,
            "deleted",
            at,
            iata=None,
            region=None,
            created=Stamp(by=TOMBSTONE_BY, at=record.created.at),
            started=None,
            live=None,
            suspended=None,
            suspend_reason=None,
            ops_managers=[],
            assistant=None,
            model_key=None,
            policy_confirmed=None,
            sra=None,
            restarts={},
            chain_checked=None,
        )

    return await _change(store, icao, edit)


# --- settings ---------------------------------------------------------------------------


def _changeable(record: TenantRecord) -> None:
    if record.state == "suspended":
        raise HostedRefused(403, "tenant_suspended", f"{record.name} is suspended: read only")
    if record.state not in _CHANGEABLE:
        raise wrong_state(record)


async def set_assistant(
    store: Store,
    icao: str,
    assistant: TenantAssistant,
    *,
    by: str,
    settings: Settings,
    space: Space,
    at: datetime,
) -> TenantRecord:
    check_assistant(assistant, settings)

    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        return record.model_copy(update={"assistant": assistant})

    updated = await _change(store, icao, edit)
    await _note(
        space,
        by=by,
        action=AuditAction.ASSISTANT_CHANGED,
        after={
            "model": assistant.model,
            "model_lite": assistant.model_lite,
            "reserve_share": assistant.reserve_share,
            "daily_limits": assistant.daily_limits,
        },
    )
    return updated


async def set_key(
    store: Store, icao: str, sealed: SealedKey | None, *, by: str, space: Space, at: datetime
) -> TenantRecord:
    """A sealed key, or None to remove it. The audit entry says only that it changed."""

    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        return record.model_copy(update={"model_key": sealed})

    updated = await _change(store, icao, edit)
    action = AuditAction.MODEL_KEY_SET if sealed is not None else AuditAction.MODEL_KEY_REMOVED
    await _note(space, by=by, action=action)
    return updated


async def set_policy_version(
    store: Store,
    icao: str,
    changes: Sequence[PolicyChange],
    *,
    base_version: int,
    note: str | None,
    base_policy: OperatorPolicy,
    by: str,
    space: Space,
    at: datetime,
) -> TenantRecord:
    """A new policy version n+1 from the version the editor saw (else 409
    ``version_conflict``). Confirmation is cleared; an acceptance under the SRA stays on the
    version it named, so the label is ILLUSTRATIVE again."""
    hosted_policy.check_changes(base_policy, changes)
    current = await get_tenant(store, icao)
    if current is None:
        raise _missing()
    _changeable(current)
    if current.policy_version != base_version:
        raise _version_conflict()
    new = base_version + 1
    with space.bound():
        before = await hosted_policy.get_version(space.store, base_version)
        await hosted_policy.put_version(
            space.store,
            PolicyVersion(
                version=new,
                base_policy_id=base_policy.policy_id,
                base_version=base_policy.version,
                changes=list(changes),
                created=Stamp(by=by, at=at),
                note=note,
            ),
        )

    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        if record.policy_version != base_version:
            raise _version_conflict()
        return record.model_copy(update={"policy_version": new, "policy_confirmed": None})

    updated = await _change(store, icao, edit)
    await _note(
        space,
        by=by,
        action=AuditAction.POLICY_CHANGED,
        note=f"Policy v{new}: {_change_words(base_policy, before, changes)}",
        after={"version": new},
    )
    return updated


def _version_conflict() -> HostedRefused:
    return HostedRefused(409, "version_conflict", "The policy changed meanwhile; load it again")


def _change_words(
    base: OperatorPolicy, before: PolicyVersion | None, changes: Sequence[PolicyChange]
) -> str:
    """``name old -> new`` for each value that moved since the version before."""
    values = {name: value.value for name, value in base.named_values().items()}
    then = values | {c.name: c.value for c in ([] if before is None else before.changes)}
    now = values | {c.name: c.value for c in changes}
    moved = [f"{n} {then[n]} -> {now[n]}" for n in sorted(now) if now[n] != then[n]]
    return "; ".join(moved) or "no value changed"


async def confirm_policy(
    store: Store, icao: str, *, version: int, by: str, space: Space, at: datetime
) -> TenantRecord:
    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        if record.policy_version != version:
            raise _version_conflict()
        return record.model_copy(
            update={"policy_confirmed": PolicyConfirmed(by=by, at=at, version=version)}
        )

    updated = await _change(store, icao, edit)
    await _note(
        space, by=by, action=AuditAction.POLICY_CONFIRMED, note=f"Policy v{version} confirmed"
    )
    return updated


async def record_sra(
    store: Store,
    icao: str,
    *,
    version: int,
    accepted_by: str,
    accepted_on: date,
    sra_ref: str | None,
    by: str,
    space: Space,
    at: datetime,
) -> TenantRecord:
    """The airline records that the current version is accepted under its SRA (TEPHRA does
    not check it). A date in the future is refused."""
    if accepted_on > at.date():
        raise HostedRefused(422, "future_date", "The acceptance date is in the future")
    acceptance = SraAcceptance(
        version=version,
        accepted_by=accepted_by,
        accepted_on=accepted_on,
        sra_ref=sra_ref,
        recorded=Stamp(by=by, at=at),
    )

    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        if record.policy_version != version:
            raise _version_conflict()
        return record.model_copy(update={"sra": acceptance})

    updated = await _change(store, icao, edit)
    await _note(
        space,
        by=by,
        action=AuditAction.SRA_RECORDED,
        note=f"Policy v{version} accepted under the airline's SRA (recorded by the airline)",
        after={"version": version, "sra_ref": sra_ref},
    )
    return updated


async def withdraw_sra(
    store: Store, icao: str, *, reason: str, by: str, space: Space, at: datetime
) -> TenantRecord:
    def edit(record: TenantRecord) -> TenantRecord:
        _changeable(record)
        if record.sra is None:
            raise HostedRefused(409, "no_acceptance", "No acceptance is recorded")
        return record.model_copy(update={"sra": None})

    updated = await _change(store, icao, edit)
    await _note(space, by=by, action=AuditAction.SRA_WITHDRAWN, note=reason)
    return updated


# --- bookkeeping ------------------------------------------------------------------------


async def note_restart(store: Store, icao: str, *, at: datetime) -> int:
    """Count a runtime restart on today's Pacific day; returns today's count."""
    day = quota_day(at).isoformat()

    def edit(record: TenantRecord) -> TenantRecord:
        return record.model_copy(update={"restarts": {day: record.restarts.get(day, 0) + 1}})

    updated = await _change(store, icao, edit)
    return updated.restarts[day]


async def note_chain_checked(store: Store, icao: str, *, by: str, at: datetime) -> TenantRecord:
    def edit(record: TenantRecord) -> TenantRecord:
        return record.model_copy(update={"chain_checked": Stamp(by=by, at=at)})

    return await _change(store, icao, edit)


# --- views ------------------------------------------------------------------------------


async def hosted_me(
    store: Store, login: AirlineLogin, record: AirlineRecord | None, *, max_airlines: int
) -> HostedMe:
    """``GET /api/hosted/me``: the login's airlines, and what its own airline may do next."""
    found = await store.query(
        Collection.HOSTED_MEMBERS, [Where("login_key", "==", login.login_key)], limit=50
    )
    rows: list[Membership] = []
    held: TenantRecord | None = None
    for doc in found:
        member = Member.model_validate(doc)
        tenant = await get_tenant(store, member.icao)
        if tenant is None or tenant.state in ("deleting", "deleted"):
            continue
        role = effective(member, tenant).role
        rows.append(Membership(icao=tenant.icao, name=tenant.name, role=role, state=tenant.state))
    can_set_up: CanSetUp | None = None
    waiting = None
    if record is not None and record.status == "verified" and record.answers is not None:
        airline = record.answers.airline
        held = await get_tenant(store, airline.icao)
        free = held is None or held.state == "deleted"
        if free and record.hosting is None:
            waiting = "hosting_not_approved"
        elif free:
            can_set_up = CanSetUp(icao=airline.icao, name=airline.name)
    return HostedMe(
        memberships=sorted(rows, key=lambda row: row.icao),
        can_set_up=can_set_up,
        waiting=waiting,
        max_airlines=max_airlines,
    )


def header(
    record: TenantRecord,
    you: Member,
    memberships: Sequence[Membership],
    *,
    running: bool,
    last_tick_wall_at: datetime | None,
    failures: int,
    problem: str | None,
    paused: PausedLine | None,
    chain: ChainHead | None,
    wall_now: datetime,
) -> TenantHeader:
    """The airline header every ``/a/<ICAO>/`` page draws (the registry fills the runtime and
    pause facts; the chain is the head the airline's store holds, never a walk)."""
    updating = (
        running
        and last_tick_wall_at is not None
        and wall_now - last_tick_wall_at <= UPDATING_WITHIN
    )
    suspended = None
    if record.state == "suspended" and record.suspended is not None:
        suspended = SuspendedLine(
            at=record.suspended.at,
            reason=record.suspend_reason or "",
            delete_after=record.suspended.at + DELETE_AFTER,
        )
    return TenantHeader(
        icao=record.icao,
        name=record.name,
        iata=record.iata,
        state=record.state,
        state_since=record.state_since,
        wall_now=wall_now,
        you=You(name=you.display_name, role=you.role, member_id=you.id),
        memberships=list(memberships),
        runtime=RuntimeLine(
            running=running,
            last_tick_wall_at=last_tick_wall_at,
            failures=failures,
            problem=problem,
            updating=updating,
        ),
        paused=paused,
        suspended=suspended,
        live=None
        if record.live is None
        else LiveLine(by=shown_by(record.live.by), at=record.live.at),
        chain=_chain_line(chain),
        policy=PolicyLine(
            version=record.policy_version,
            label=hosted_policy.label_for(record, record.policy_version),
        ),
        started=LiveLine(by=shown_by(record.started.by), at=record.started.at)
        if record.started is not None and record.state in ("shadow", "live")
        else None,
    )


def _real_problems(head: ChainHead) -> list[str]:
    """A head restored at start is "not yet walked": that is not a break."""
    return [problem for problem in head.problems if problem != audit.NOT_WALKED]


def _chain_line(head: ChainHead | None) -> ChainLine:
    if head is None:
        return ChainLine(intact=True, entries=0, checked_at=None)
    return ChainLine(
        intact=not _real_problems(head), entries=head.entries, checked_at=head.checked_at
    )


async def record_page(
    space: Space, *, before_seq: int | None, limit: int = RECORD_PAGE
) -> tuple[list[AuditEntry], int | None]:
    """Newest first, ``limit`` entries before ``before_seq`` (``Store.page``), and the cursor
    for the next page (None at the first entry)."""
    with space.bound():
        docs = await space.store.page(
            Collection.AUDIT, field="seq", before=before_seq, limit=limit, descending=True
        )
    entries = [audit.ChainedAuditEntry.model_validate(doc) for doc in docs]
    last = entries[-1].seq if entries else None
    more = len(entries) == limit and last is not None and last > 1
    return list(entries), last if more else None


def record_tab(
    entries: Sequence[AuditEntry],
    next_before_seq: int | None,
    held: audit.AuditChain,
    *,
    is_ops_manager: bool,
    can_check: bool,
    can_export: bool,
) -> RecordTab:
    """The Record tab from the head this process holds for the airline's store (never a
    walk), with how far a walk has found it intact."""
    head = held.head
    shown: RecordHead | None = None
    if head is not None:
        problems = _real_problems(head)
        through = held.verified_through_seq or None
        shown = RecordHead(
            intact=not problems,
            entries=head.entries,
            head_seq=head.seq,
            head_sha256=head.sha256,
            verified_through_seq=through,
            checked_at=head.checked_at,
            problems=problems,
            note="Entries after the last walk are linked as they are written; "
            "Check the whole chain walks every entry."
            if through is None or through < head.seq
            else "The whole chain was walked through its newest entry.",
        )
    return RecordTab(
        entries=list(entries),
        head=shown,
        next_before_seq=next_before_seq,
        can_check=is_ops_manager and can_check,
        can_export=is_ops_manager and can_export,
    )
