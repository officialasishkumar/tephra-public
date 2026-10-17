"""People of a hosted airline (SPEC §3.5): one-time invites bound to an email, joining,
display names, roles with at least one ops manager kept under a race, revoke-on-remove,
member-only logins, and the operator's ops-manager invite. No email in any audit entry."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest

from tephra.airline import accounts
from tephra.airline.models import AirlineLogin
from tephra.hosted import members, tenants
from tephra.hosted.models import HostedRefused, Member
from tephra.models import AuditAction
from tephra.store.base import Collection
from tests.test_hosted_tenants import OPERATOR, World, chain_of, set_up, wall, world


async def login_for(w: World, email: str) -> AirlineLogin:
    """A member-only login, made as the join page makes one."""
    return await accounts.create_member_login(
        w.root, email=email, password_hash="scrypt$test", recovery_sha256="0" * 64, at=wall()
    )


async def joined(w: World, by: Member, email: str, name: str, role: str = "dispatcher") -> Member:
    _, token = await members.invite(
        w.root,
        "RFB",
        email,
        role,
        by=by,
        space=w.space("RFB"),
        at=wall(),  # type: ignore[arg-type]
    )
    login = await login_for(w, email)
    return await members.accept(
        w.root, token, login, name, space=w.space("RFB"), access=w.access, at=wall()
    )


async def test_an_invite_works_once_for_its_email(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    made, token = await members.invite(
        w.root, "RFB", "Dee@RFB.example", "dispatcher", by=ana, space=w.space("RFB"), at=wall()
    )
    assert made.email == "dee@rfb.example"
    assert made.created_by == ana.id
    stored = await w.root.get(Collection.HOSTED_INVITES, made.sha256)
    assert stored is not None
    assert token not in json.dumps(stored)
    view = await members.invite_view(w.root, token, at=wall())
    assert view.email_hint == "d•••@rfb.example"
    assert view.invited_by == "Ana Ops"
    eve = await login_for(w, "eve@rfb.example")
    with pytest.raises(HostedRefused) as refused:
        await members.accept(
            w.root, token, eve, "Eve", space=w.space("RFB"), access=w.access, at=wall()
        )
    assert (refused.value.status, refused.value.code) == (403, "wrong_email")
    dee = await login_for(w, "dee@rfb.example")
    member = await members.accept(
        w.root, token, dee, "Dee Disp", space=w.space("RFB"), access=w.access, at=wall()
    )
    assert member.role == "dispatcher"
    assert member.invited_by == ana.id
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.accept(
            w.root, token, dee, "Dee Disp", space=w.space("RFB"), access=w.access, at=wall()
        )
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.invite_view(w.root, token, at=wall())
    await w.aclose()


async def test_an_expired_or_revoked_invite_is_gone_alike(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    _, late = await members.invite(
        w.root, "RFB", "dee@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    dee = await login_for(w, "dee@rfb.example")
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.accept(
            w.root,
            late,
            dee,
            "Dee",
            space=w.space("RFB"),
            access=w.access,
            at=wall() + members.INVITE_LIFE + timedelta(seconds=1),
        )
    made, token = await members.invite(
        w.root, "RFB", "sam@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    left = await members.revoke_invite(
        w.root, "RFB", made.id, by=ana, space=w.space("RFB"), at=wall()
    )
    assert made.id not in [i.id for i in left]
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.invite_view(w.root, token, at=wall())
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.invite_view(w.root, "x" * 43, at=wall())
    await w.aclose()


async def test_two_accepts_of_one_link_make_one_member(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    _, token = await members.invite(
        w.root, "RFB", "dee@rfb.example", "dispatcher", by=ana, space=w.space("RFB"), at=wall()
    )
    dee = await login_for(w, "dee@rfb.example")
    results = await asyncio.gather(
        *(
            members.accept(
                w.root, token, dee, "Dee", space=w.space("RFB"), access=w.access, at=wall()
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, Member) for r in results) == 1
    assert [r.code for r in results if isinstance(r, HostedRefused)] == ["invite_gone"]
    assert len(await members.members_of(w.root, "RFB")) == 2
    await w.aclose()


async def test_display_names_are_unique_among_members(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    _, token = await members.invite(
        w.root, "RFB", "dee@rfb.example", "dispatcher", by=ana, space=w.space("RFB"), at=wall()
    )
    dee = await login_for(w, "dee@rfb.example")
    with pytest.raises(HostedRefused, match="name_taken"):
        await members.accept(
            w.root, token, dee, "ana ops", space=w.space("RFB"), access=w.access, at=wall()
        )
    await w.aclose()


async def test_members_and_invites_have_limits(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    for n in range(members.MAX_OPEN_INVITES):
        await members.invite(
            w.root, "RFB", f"p{n}@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
        )
    with pytest.raises(HostedRefused, match="too_many_invites"):
        await members.invite(
            w.root, "RFB", "late@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
        )
    with pytest.raises(HostedRefused, match="already_member"):
        await members.invite(
            w.root, "RFB", "ana@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
        )
    await w.aclose()


async def test_removing_an_ops_manager_revokes_the_invites_they_made(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    bo = await joined(w, ana, "bo@rfb.example", "Bo Ops", "ops_manager")
    _made, token = await members.invite(
        w.root, "RFB", "sam@rfb.example", "dispatcher", by=bo, space=w.space("RFB"), at=wall()
    )
    left = await members.remove(
        w.root, "RFB", bo.id, by=ana, space=w.space("RFB"), access=w.access, at=wall()
    )
    assert [m.id for m in left] == [ana.id]
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.invite_view(w.root, token, at=wall())
    actions = [e.action for e in await chain_of(w, "RFB")]
    assert actions[-2:] == [AuditAction.INVITE_REVOKED, AuditAction.MEMBER_REMOVED]
    record = await tenants.get_tenant(w.root, "RFB")
    assert record is not None
    assert record.ops_managers == [ana.id]
    await w.aclose()


async def test_two_ops_managers_demoting_each_other_leave_one(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    bo = await joined(w, ana, "bo@rfb.example", "Bo Ops", "ops_manager")
    results = await asyncio.gather(
        members.set_role(
            w.root,
            "RFB",
            ana.id,
            "dispatcher",
            by=bo,
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        ),
        members.set_role(
            w.root,
            "RFB",
            bo.id,
            "dispatcher",
            by=ana,
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        ),
        return_exceptions=True,
    )
    assert [r.code for r in results if isinstance(r, HostedRefused)] == ["last_ops_manager"]
    record = await tenants.get_tenant(w.root, "RFB")
    assert record is not None
    assert len(record.ops_managers) == 1
    roles = {m.id: m.role for m in await members.members_of(w.root, "RFB", record=record)}
    assert sorted(roles.values()) == ["dispatcher", "ops_manager"]
    await w.aclose()


async def test_the_last_ops_manager_cannot_leave_or_be_demoted(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    with pytest.raises(HostedRefused, match="last_ops_manager"):
        await members.leave(w.root, "RFB", ana.id, space=w.space("RFB"), access=w.access, at=wall())
    with pytest.raises(HostedRefused, match="last_ops_manager"):
        await members.set_role(
            w.root,
            "RFB",
            ana.id,
            "viewer",
            by=ana,
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        )
    await w.aclose()


async def test_join_makes_a_member_only_login(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    _, token = await members.invite(
        w.root, "RFB", "vic@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    login, member, code = await members.join(
        w.root,
        token,
        "vic@rfb.example",
        "a long password 1",
        "Vic View",
        space=w.space("RFB"),
        access=w.access,
        at=wall(),
    )
    assert login.airline_id is None
    assert member.role == "viewer"
    assert len(code) == 19
    stored = await accounts.get_login(w.root, login.login_key)
    assert stored is not None
    assert stored.airline_id is None
    with pytest.raises(HostedRefused, match="invite_gone"):
        await members.join(
            w.root,
            token,
            "vic@rfb.example",
            "a long password 1",
            "Vic Two",
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        )
    await w.aclose()


async def test_join_with_a_taken_email_says_sign_in_and_leaves_nothing(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    await login_for(w, "dee@rfb.example")
    _, token = await members.invite(
        w.root, "RFB", "dee@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    with pytest.raises(HostedRefused, match="email_taken"):
        await members.join(
            w.root,
            token,
            "dee@rfb.example",
            "a long password 1",
            "Dee",
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        )
    with pytest.raises(HostedRefused, match="wrong_email"):
        await members.join(
            w.root,
            token,
            "eve@rfb.example",
            "a long password 1",
            "Eve",
            space=w.space("RFB"),
            access=w.access,
            at=wall(),
        )
    assert await accounts.get_login(w.root, accounts.login_key("eve@rfb.example")) is None
    await w.aclose()


async def test_an_operator_restores_an_ops_manager_to_the_record_holder(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, _, ana_login = await set_up(w)
    dee = await joined(w, ana, "dee@rfb.example", "Dee Disp", "ops_manager")
    await members.set_role(
        w.root,
        "RFB",
        ana.id,
        "dispatcher",
        by=dee,
        space=w.space("RFB"),
        access=w.access,
        at=wall(),
    )
    made, token = await members.ops_manager_invite(
        w.root, "RFB", by_operator=OPERATOR, space=w.space("RFB"), at=wall()
    )
    assert made.email == "ana@rfb.example"
    assert made.created_by == "operator:4f1c2a9b"
    promoted = await members.accept(
        w.root, token, ana_login, "ignored", space=w.space("RFB"), access=w.access, at=wall()
    )
    assert promoted.role == "ops_manager"
    assert promoted.display_name == "Ana Ops"
    record = await tenants.get_tenant(w.root, "RFB")
    assert record is not None
    assert ana.id in record.ops_managers
    actions = [e.action for e in await chain_of(w, "RFB")]
    assert AuditAction.OPS_MANAGER_RESTORED in actions
    entries = json.dumps([e.model_dump(mode="json") for e in await chain_of(w, "RFB")])
    assert "@" not in entries
    await w.aclose()


async def test_the_people_tab_shows_emails_to_ops_managers_only(tmp_path: Path) -> None:
    w = world(tmp_path)
    _tenant, ana, *_ = await set_up(w)
    dee = await joined(w, ana, "dee@rfb.example", "Dee Disp")
    await members.invite(
        w.root, "RFB", "sam@rfb.example", "viewer", by=ana, space=w.space("RFB"), at=wall()
    )
    record = await tenants.get_tenant(w.root, "RFB")
    assert record is not None
    seen_by_ana = await members.people_tab(w.root, record, ana, at=wall())
    assert [m.email for m in seen_by_ana.members] == ["ana@rfb.example", "dee@rfb.example"]
    assert seen_by_ana.invites[0].email == "sam@rfb.example"
    seen_by_dee = await members.people_tab(w.root, record, dee, at=wall())
    assert {m.email for m in seen_by_dee.members} == {None}
    assert seen_by_dee.invites[0].email is None
    assert [m.you for m in seen_by_dee.members] == [False, True]
    await w.aclose()


async def test_a_member_only_login_leaves_everything_when_deleted(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, *_ = await set_up(w)
    dee = await joined(w, ana, "dee@rfb.example", "Dee Disp")
    login = await accounts.get_login(w.root, dee.login_key)
    assert login is not None
    await members.delete_member_login(w.root, login, spaces=w.space, access=w.access, at=wall())
    assert await accounts.get_login(w.root, dee.login_key) is None
    assert [m.id for m in await members.members_of(w.root, "RFB")] == [ana.id]
    await w.aclose()
