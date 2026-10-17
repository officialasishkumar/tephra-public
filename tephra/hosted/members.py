"""The people of a hosted airline: members, one-time invite links, roles (SPEC §3.5).

An invite is a link the inviter copies (no email is sent, and emails are not verified). Only
the token's SHA-256 is stored; the link lives 72 hours and works once, and only for a login
with the invited email. Marking it used is a compare-and-set, and the member is written after
it, so two people opening one link make one member. Ops managers are whoever
``TenantRecord.ops_managers`` names: every role change, removal or leave is a compare-and-set on
the record that keeps at least one (S14), and the member document follows. A member who
stops being an ops manager loses the invites they made (S13). Audit entries name people by
display name and member id, never by email; every change empties the access cache for the
people it concerns.
"""

import hashlib
import secrets
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from pydantic import ValidationError

from tephra.airline import accounts, passwords
from tephra.airline.models import AirlineLogin, Stamp
from tephra.desk import audit
from tephra.hosted.access import AccessCache, effective, member_doc_id
from tephra.hosted.models import (
    HostedRefused,
    HostedRole,
    Invite,
    InviteRow,
    InviteView,
    InviteYou,
    Member,
    MemberRow,
    PeopleLimits,
    PeopleTab,
    Space,
    TenantRecord,
)
from tephra.hosted.tenants import (
    actor_of,
    display_name,
    get_tenant,
    member_by,
    member_id,
    wrong_state,
)
from tephra.models import AuditAction
from tephra.store.base import Collection, Store, Where

__all__ = [
    "INVITE_LIFE",
    "MAX_MEMBERS",
    "MAX_OPEN_INVITES",
    "accept",
    "delete_member_login",
    "email_hint",
    "invite",
    "invite_by_token",
    "invite_view",
    "invites_of",
    "join",
    "leave",
    "member",
    "members_of",
    "memberships",
    "open_invites",
    "ops_manager_invite",
    "people_tab",
    "remove",
    "revoke_invite",
    "set_role",
    "usable",
]

INVITE_LIFE: Final = timedelta(hours=72)
MAX_MEMBERS: Final = 50
MAX_OPEN_INVITES: Final = 20
_ACTIVE: Final = frozenset({"setup", "shadow", "live"})


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def email_hint(email: str) -> str:
    """``d•••@rfb.example``: enough to recognise one's own address, not to harvest it."""
    local, _, domain = email.partition("@")
    return f"{local[:1]}•••@{domain}"


def usable(invite: Invite, at: datetime) -> bool:
    return invite.used is None and invite.revoked is None and invite.expires_at > at


def _gone() -> HostedRefused:
    return HostedRefused(
        404,
        "invite_gone",
        "This invite link is used, revoked or expired. Ask your ops manager for a new one.",
    )


# --- reads ------------------------------------------------------------------------------


def _members(docs: Sequence[dict[str, Any]], record: TenantRecord | None) -> list[Member]:
    found: list[Member] = []
    for doc in docs:
        try:
            parsed = Member.model_validate(doc)
        except ValidationError:
            continue
        found.append(parsed if record is None else effective(parsed, record))
    return sorted(found, key=lambda m: (m.joined_at, m.id))


async def members_of(
    store: Store, icao: str, *, record: TenantRecord | None = None
) -> list[Member]:
    """Oldest first; with ``record`` the roles follow ``record.ops_managers``."""
    docs = await store.query(
        Collection.HOSTED_MEMBERS, [Where("icao", "==", icao)], limit=MAX_MEMBERS + 10
    )
    return _members(docs, record)


async def memberships(store: Store, login_key: str) -> list[Member]:
    docs = await store.query(
        Collection.HOSTED_MEMBERS, [Where("login_key", "==", login_key)], limit=50
    )
    return _members(docs, None)


async def member(store: Store, icao: str, login_key: str) -> Member | None:
    doc = await store.get(Collection.HOSTED_MEMBERS, member_doc_id(icao, login_key))
    return None if doc is None else Member.model_validate(doc)


async def invites_of(store: Store, icao: str) -> list[Invite]:
    docs = await store.query(Collection.HOSTED_INVITES, [Where("icao", "==", icao)], limit=200)
    found = [Invite.model_validate(doc) for doc in docs]
    return sorted(found, key=lambda i: (i.created.at, i.id))


async def open_invites(store: Store, icao: str, *, at: datetime) -> list[Invite]:
    return [i for i in await invites_of(store, icao) if usable(i, at)]


async def invite_by_token(store: Store, token: str) -> Invite | None:
    """The invite a token stands for, used or not (``usable`` says whether it still works)."""
    doc = await store.get(Collection.HOSTED_INVITES, _sha(token))
    return None if doc is None else Invite.model_validate(doc)


# --- helpers ----------------------------------------------------------------------------


async def _active_tenant(store: Store, icao: str) -> TenantRecord:
    record = await get_tenant(store, icao)
    if record is None or record.state in ("deleting", "deleted"):
        raise HostedRefused(404, "no_such_airline", "No such airline on this site")
    if record.state == "suspended":
        raise HostedRefused(403, "tenant_suspended", f"{record.name} is suspended: read only")
    if record.state not in _ACTIVE:
        raise wrong_state(record)
    return record


async def _note(
    space: Space, *, by: str, action: AuditAction, note: str, after: dict[str, Any] | None = None
) -> None:
    with space.bound():
        await audit.record(space.store, actor=actor_of(by), action=action, note=note, after=after)


def _by(actor: Member | str) -> tuple[str, str]:
    """(stamp, created_by) for a member or an operator's stamp ``operator:<name>#<k8>``."""
    if isinstance(actor, Member):
        return member_by(actor), actor.id
    return actor, "operator:" + actor.rpartition("#")[2]


async def _update_record(
    store: Store, icao: str, edit: Callable[[TenantRecord], TenantRecord]
) -> TenantRecord:
    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise HostedRefused(404, "no_such_airline", "No such airline on this site")
        record = TenantRecord.model_validate(stored)
        edited = edit(record)
        return edited.model_copy(update={"version": record.version + 1}).model_dump(mode="json")

    return TenantRecord.model_validate(await store.update(Collection.HOSTED_TENANTS, icao, change))


def _find(members: Sequence[Member], wanted: str) -> Member:
    found = next((m for m in members if m.id == wanted), None)
    if found is None:
        raise HostedRefused(404, "not_found", "No such member")
    return found


def _check_name(name: str, members: Sequence[Member], *, besides: str | None = None) -> str:
    shown = display_name(name)
    taken = {m.display_name.casefold() for m in members if m.login_key != besides}
    if shown.casefold() in taken:
        raise HostedRefused(409, "name_taken", "Another member uses that display name")
    return shown


async def _revoke_made_by(
    store: Store, icao: str, made_by: Member, *, by: str, space: Space, at: datetime
) -> int:
    """Revoke every open invite ``made_by`` created (S13); returns how many."""
    count = 0
    for found in await open_invites(store, icao, at=at):
        if found.created_by != made_by.id:
            continue
        if await _revoke(store, found, by=by, at=at):
            await _note(
                space,
                by=by,
                action=AuditAction.INVITE_REVOKED,
                note=f"{found.id} {found.role}: its maker {made_by.id} no longer may invite",
            )
            count += 1
    return count


async def _revoke(store: Store, target: Invite, *, by: str, at: datetime) -> bool:
    """Mark ``target`` revoked unless it was used or revoked meanwhile; True when it was."""
    revoked = False

    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        nonlocal revoked
        if stored is None:
            raise _gone()
        held = Invite.model_validate(stored)
        revoked = held.used is None and held.revoked is None
        if not revoked:
            return held.model_dump(mode="json")
        return held.model_copy(update={"revoked": Stamp(by=by, at=at)}).model_dump(mode="json")

    await store.update(Collection.HOSTED_INVITES, target.sha256, change)
    return revoked


async def _new_invite(
    store: Store,
    record: TenantRecord,
    email: str,
    role: HostedRole,
    *,
    stamp: str,
    created_by: str,
    at: datetime,
    promotes: bool = False,
) -> tuple[Invite, str]:
    """``promotes``: an operator's restore, which also reaches a member who is not an ops
    manager now."""
    members = await members_of(store, record.icao, record=record)
    key = accounts.login_key(email)
    held = next((m for m in members if m.login_key == key), None)
    if held is not None and not (promotes and held.role != "ops_manager"):
        raise HostedRefused(409, "already_member", "That email is already a member")
    if held is None and len(members) >= MAX_MEMBERS:
        raise HostedRefused(409, "members_full", f"An airline has at most {MAX_MEMBERS} members")
    if len(await open_invites(store, record.icao, at=at)) >= MAX_OPEN_INVITES:
        raise HostedRefused(
            409, "too_many_invites", f"At most {MAX_OPEN_INVITES} invites may be open at once"
        )
    token = secrets.token_urlsafe(32)
    made = Invite(
        id="IV-" + secrets.token_hex(5),
        sha256=_sha(token),
        icao=record.icao,
        email=email.strip().lower(),
        role=role,
        created=Stamp(by=stamp, at=at),
        created_by=created_by,
        expires_at=at + INVITE_LIFE,
    )

    def create(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is not None:
            raise RuntimeError("an invite token was drawn twice")
        return made.model_dump(mode="json")

    await store.update(Collection.HOSTED_INVITES, made.sha256, create)
    return made, token


# --- invites ----------------------------------------------------------------------------


async def invite(
    store: Store,
    icao: str,
    email: str,
    role: HostedRole,
    *,
    by: Member | str,
    space: Space,
    at: datetime,
) -> tuple[Invite, str]:
    """A one-time link for ``email`` as ``role``; the token is returned once, never stored."""
    record = await _active_tenant(store, icao)
    stamp, created_by = _by(by)
    made, token = await _new_invite(
        store, record, email, role, stamp=stamp, created_by=created_by, at=at
    )
    await _note(space, by=stamp, action=AuditAction.MEMBER_INVITED, note=f"{made.id} {role}")
    return made, token


async def ops_manager_invite(
    store: Store, icao: str, *, by_operator: str, space: Space, at: datetime
) -> tuple[Invite, str]:
    """An operator's way out when no ops manager is left: an ops-manager invite to the airline
    record holder's email. Accepting it needs that account signed in."""
    record = await _active_tenant(store, icao)
    holder = await accounts.get_record(store, record.airline_id)
    made, token = await _new_invite(
        store,
        record,
        holder.email,
        "ops_manager",
        stamp=by_operator,
        created_by="operator:" + by_operator.rpartition("#")[2],
        at=at,
        promotes=True,
    )
    await _note(
        space,
        by=by_operator,
        action=AuditAction.OPS_MANAGER_RESTORED,
        note=f"{made.id} ops_manager, for the airline's account holder",
    )
    return made, token


async def revoke_invite(
    store: Store, icao: str, invite_id: str, *, by: Member | str, space: Space, at: datetime
) -> list[Invite]:
    """Returns the invites still open."""
    await _active_tenant(store, icao)
    target = next((i for i in await open_invites(store, icao, at=at) if i.id == invite_id), None)
    if target is None:
        raise HostedRefused(404, "not_found", "No such open invite")
    stamp, _ = _by(by)
    if await _revoke(store, target, by=stamp, at=at):
        await _note(space, by=stamp, action=AuditAction.INVITE_REVOKED, note=f"{target.id}")
    return await open_invites(store, icao, at=at)


async def invite_view(
    store: Store, token: str, *, at: datetime, login: AirlineLogin | None = None
) -> InviteView:
    """What the join page shows before anyone signs in (404 ``invite_gone`` alike for an
    unknown, used, revoked or expired link, and for an airline no longer hosted). With the
    browser's ``login`` it also says who that is, masked, and whether the invite is for it."""
    found = await invite_by_token(store, token)
    if found is None or not usable(found, at):
        raise _gone()
    record = await get_tenant(store, found.icao)
    if record is None or record.state not in (*_ACTIVE, "suspended"):
        raise _gone()
    by = found.created.by
    return InviteView(
        airline=record.name,
        icao=record.icao,
        role=found.role,
        email_hint=email_hint(found.email),
        expires_at=found.expires_at,
        invited_by="TEPHRA staff" if by.startswith("operator:") else by.split("#")[0],
        you=None if login is None else await _you(store, login, found),
    )


async def _you(store: Store, login: AirlineLogin, invite: Invite) -> InviteYou:
    """The signed-in login as the join page names it, with the name it already uses on TEPHRA
    (its first membership's) to start the name field from."""
    held = await store.query(
        Collection.HOSTED_MEMBERS, [Where("login_key", "==", login.login_key)], limit=1
    )
    name = None
    if held:
        try:
            name = Member.model_validate(held[0]).display_name
        except ValidationError:
            name = None
    return InviteYou(
        email_hint=email_hint(login.email),
        for_you=login.email.lower() == invite.email,
        name=name,
    )


# --- joining ----------------------------------------------------------------------------


async def accept(
    store: Store,
    token: str,
    login: AirlineLogin,
    name: str,
    *,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> Member:
    """A signed-in login takes the invite meant for its email. Marking the invite used is a
    compare-and-set; the member is written after it (two accepts make one member). An
    operator's ops-manager invite promotes a holder who is already a member."""
    found = await invite_by_token(store, token)
    if found is None or not usable(found, at):
        raise _gone()
    try:
        record = await _active_tenant(store, found.icao)
    except HostedRefused as refused:
        if refused.code == "no_such_airline":
            raise _gone() from None
        raise
    if login.email.strip().lower() != found.email:
        raise HostedRefused(403, "wrong_email", "This invite is for another email address")
    members = await members_of(store, record.icao, record=record)
    held = next((m for m in members if m.login_key == login.login_key), None)
    restoring = found.role == "ops_manager" and found.created_by.startswith("operator:")
    if held is not None and not restoring:
        raise HostedRefused(409, "already_member", "You are already a member")
    if held is None and len(members) >= MAX_MEMBERS:
        raise HostedRefused(409, "members_full", f"An airline has at most {MAX_MEMBERS} members")
    mid = member_id(record.icao, login.login_key)
    shown = held.display_name if held is not None else _check_name(name, members, besides=None)
    stamp = f"{shown}#{mid}"

    def use(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise _gone()
        current = Invite.model_validate(stored)
        if not usable(current, at):
            raise _gone()
        return current.model_copy(update={"used": Stamp(by=stamp, at=at)}).model_dump(mode="json")

    await store.update(Collection.HOSTED_INVITES, found.sha256, use)
    if found.role == "ops_manager":

        def promote(current: TenantRecord) -> TenantRecord:
            if mid in current.ops_managers:
                return current
            return current.model_copy(update={"ops_managers": [*current.ops_managers, mid]})

        await _update_record(store, record.icao, promote)
    joined = (
        held.model_copy(update={"role": "ops_manager"})
        if held is not None
        else Member(
            id=mid,
            icao=record.icao,
            login_key=login.login_key,
            email=login.email,
            display_name=shown,
            role=found.role,
            joined_at=at,
            invited_by=found.created_by,
        )
    )
    await store.put(
        Collection.HOSTED_MEMBERS,
        member_doc_id(record.icao, login.login_key),
        joined.model_dump(mode="json"),
    )
    access.drop(login_key=login.login_key)
    action = AuditAction.MEMBER_ROLE_CHANGED if held is not None else AuditAction.MEMBER_JOINED
    await _note(space, by=stamp, action=action, note=f"{found.id} {mid} as {found.role}")
    return joined


async def join(
    store: Store,
    token: str,
    email: str,
    password: str,
    name: str,
    *,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> tuple[AirlineLogin, Member, str]:
    """A new member-only login for the invited email, then :func:`accept`. Also returns the
    login's recovery code (shown once, as an account's is); the login is removed again when
    the accept fails."""
    found = await invite_by_token(store, token)
    if found is None or not usable(found, at):
        raise _gone()
    email = email.strip().lower()
    if email != found.email:
        raise HostedRefused(403, "wrong_email", "This invite is for another email address")
    record = await get_tenant(store, found.icao)
    if record is None or record.state not in _ACTIVE:
        raise _gone()
    _check_name(name, await members_of(store, record.icao, record=record))
    code = passwords.new_recovery_code()
    try:
        login = await accounts.create_member_login(
            store,
            email=email,
            password_hash=await passwords.hashed(password),
            recovery_sha256=passwords.code_sha256(code),
            at=at,
        )
    except accounts.EmailTaken:
        raise HostedRefused(
            409, "email_taken", "That email has an account: sign in, then open the link again"
        ) from None
    try:
        joined = await accept(store, token, login, name, space=space, access=access, at=at)
    except BaseException:
        await store.delete(Collection.AIRLINE_LOGINS, login.login_key)
        raise
    return login, joined, code


# --- roles, removal, leaving ------------------------------------------------------------


async def _drop_ops_manager(
    store: Store, record: TenantRecord, target: Member, *, keep: bool
) -> TenantRecord:
    """The record without ``target`` among its ops managers (``keep``: with it), refused when
    that would leave none; checked inside the compare-and-set (S14)."""

    def edit(current: TenantRecord) -> TenantRecord:
        managers = [mid for mid in current.ops_managers if mid != target.id]
        if keep:
            managers = [*managers, target.id]
        elif not managers:
            raise HostedRefused(
                409, "last_ops_manager", "An airline keeps at least one ops manager"
            )
        return current.model_copy(update={"ops_managers": managers})

    return await _update_record(store, record.icao, edit)


async def set_role(
    store: Store,
    icao: str,
    target_id: str,
    role: HostedRole,
    *,
    by: Member | str,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> list[Member]:
    record = await _active_tenant(store, icao)
    target = _find(await members_of(store, icao, record=record), target_id)
    if target.role == role:
        return await members_of(store, icao, record=record)
    record = await _drop_ops_manager(store, record, target, keep=role == "ops_manager")
    await store.put(
        Collection.HOSTED_MEMBERS,
        member_doc_id(icao, target.login_key),
        target.model_copy(update={"role": role}).model_dump(mode="json"),
    )
    stamp, _ = _by(by)
    if target.role == "ops_manager":
        await _revoke_made_by(store, icao, target, by=stamp, space=space, at=at)
    access.drop(login_key=target.login_key, icao=icao)
    await _note(
        space,
        by=stamp,
        action=AuditAction.MEMBER_ROLE_CHANGED,
        note=f"{member_by(target)}: {target.role} -> {role}",
    )
    return await members_of(store, icao, record=record)


async def _remove(
    store: Store,
    record: TenantRecord,
    target: Member,
    *,
    stamp: str,
    note: str,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> list[Member]:
    record = await _drop_ops_manager(store, record, target, keep=False)
    await store.delete(Collection.HOSTED_MEMBERS, member_doc_id(record.icao, target.login_key))
    await _revoke_made_by(store, record.icao, target, by=stamp, space=space, at=at)
    access.drop(login_key=target.login_key, icao=record.icao)
    await _note(space, by=stamp, action=AuditAction.MEMBER_REMOVED, note=note)
    return await members_of(store, record.icao, record=record)


async def remove(
    store: Store,
    icao: str,
    target_id: str,
    *,
    by: Member | str,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> list[Member]:
    record = await _active_tenant(store, icao)
    target = _find(await members_of(store, icao, record=record), target_id)
    stamp, _ = _by(by)
    return await _remove(
        store,
        record,
        target,
        stamp=stamp,
        note=f"{member_by(target)} removed",
        space=space,
        access=access,
        at=at,
    )


async def leave(
    store: Store,
    icao: str,
    target_id: str,
    *,
    space: Space,
    access: AccessCache,
    at: datetime,
) -> list[Member]:
    """A member leaves (also while the airline is suspended)."""
    record = await get_tenant(store, icao)
    if record is None or record.state in ("deleting", "deleted"):
        raise HostedRefused(404, "no_such_airline", "No such airline on this site")
    target = _find(await members_of(store, icao, record=record), target_id)
    return await _remove(
        store,
        record,
        target,
        stamp=member_by(target),
        note=f"{member_by(target)} left",
        space=space,
        access=access,
        at=at,
    )


async def delete_member_login(
    store: Store,
    login: AirlineLogin,
    *,
    spaces: Callable[[str], Space],
    access: AccessCache,
    at: datetime,
) -> None:
    """A member-only login deletes itself: it leaves every airline (refused when it is the
    last ops manager of one), then the login goes."""
    if login.airline_id is not None:
        raise ValueError("an onboarding account is deleted with its record")
    if await accounts.deletion_refusal(store, login, None) is not None:
        raise HostedRefused(
            409, "last_ops_manager", "Make someone else an ops manager before you go"
        )
    for held in await memberships(store, login.login_key):
        record = await get_tenant(store, held.icao)
        if record is None or record.state == "deleted":
            await store.delete(Collection.HOSTED_MEMBERS, member_doc_id(held.icao, held.login_key))
            continue
        await leave(store, held.icao, held.id, space=spaces(held.icao), access=access, at=at)
    await store.delete(Collection.AIRLINE_LOGINS, login.login_key)
    access.drop(login_key=login.login_key)


# --- the People tab ---------------------------------------------------------------------


async def people_tab(store: Store, record: TenantRecord, you: Member, *, at: datetime) -> PeopleTab:
    """Members and open invites; emails only for ops managers ("Names never go to a model")."""
    members = await members_of(store, record.icao, record=record)
    manager = effective(you, record).role == "ops_manager"
    logins: dict[str, AirlineLogin | None] = {}
    for found in members:
        doc = await store.get(Collection.AIRLINE_LOGINS, found.login_key)
        logins[found.login_key] = None if doc is None else AirlineLogin.model_validate(doc)
    invites = await open_invites(store, record.icao, at=at)
    return PeopleTab(
        members=[
            MemberRow(
                id=m.id,
                name=m.display_name,
                email=m.email if manager else None,
                role=m.role,
                joined_at=m.joined_at,
                last_sign_in_at=None
                if (login := logins.get(m.login_key)) is None
                else login.last_sign_in_at,
                you=m.id == you.id,
            )
            for m in members
        ],
        invites=[
            InviteRow(
                id=i.id,
                email=i.email if manager else None,
                role=i.role,
                created=i.created,
                expires_at=i.expires_at,
            )
            for i in invites
        ],
        limits=PeopleLimits(members=MAX_MEMBERS, open_invites=MAX_OPEN_INVITES),
    )
