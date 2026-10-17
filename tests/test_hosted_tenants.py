"""A hosted airline's states (SPEC §3.4): set up, start, live, back, stop, suspend, resume,
delete after 7 days; the site's places under a race; each transition in the airline's own
chain on the wall clock, naming no email. The helpers here are shared by the other hosted
domain tests (``from tests.test_hosted_tenants import ...``)."""

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tephra.airline import accounts
from tephra.airline.models import AirlineAnswers, AirlineLogin, AirlineRecord, Stamp
from tephra.config import Settings
from tephra.desk import audit
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.hosted import policy as hosted_policy
from tephra.hosted import tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.feeds import ConnectionStats, FeedStats
from tephra.hosted.models import HostedRefused, Member, TenantRecord
from tephra.hosted.registry import TenantSpace
from tephra.models import AuditAction, OperatorPolicy
from tephra.policy import load_policy
from tephra.store import open_store
from tephra.store.base import Collection
from tephra.store.metered import TENANT_CACHED, MeteredStore, StoreMeter
from tephra.util import timeutil

SECRET = "hosted-test-session-secret-0123456789abcdef"
ANSWERS = Path(__file__).parent / "fixtures" / "airline" / "answers.json"
OPERATOR = "operator:M. Tan#4f1c2a9b"
_POLICY: OperatorPolicy | None = None
_AIRPORTS: AirportCatalogue | None = None


def site(tmp_path: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "sqlite_path": tmp_path / "state" / "tephra.sqlite3",
        "cache_dir": tmp_path / "cache",
        "features": "connect,crew,notices,onboard,hosted",
        "session_secret": SECRET,
        "llm": "stub",
    }
    return Settings(_env_file=None, **(values | overrides))


def base_policy() -> OperatorPolicy:
    global _POLICY
    if _POLICY is None:
        settings = Settings(_env_file=None)
        _POLICY = load_policy(settings.data_dir, settings.policy_file)
    return _POLICY


def airports() -> AirportCatalogue:
    global _AIRPORTS
    if _AIRPORTS is None:
        settings = Settings(_env_file=None)
        runway = base_policy().alternates.min_runway_m.value
        _AIRPORTS = load_airports(settings.data_dir, min_runway_m=runway)
    return _AIRPORTS


def answers(
    icao: str = "RFB",
    name: str = "Ring of Fire Charter",
    *,
    provider: str = "gemini",
    airports_list: tuple[str, ...] = ("WIII", "WADD"),
    feeds: dict[str, bool] | None = None,
) -> AirlineAnswers:
    """Fictional: Ring of Fire Charter (RFB), Cargo (RFC) and friends."""
    data = json.loads(ANSWERS.read_text())
    data["airline"] |= {
        "name": name,
        "icao": icao,
        "iata": "RB" if icao == "RFB" else None,
        "callsign_prefix": icao,
        "ops_email": f"ops@{icao.lower()}.example",
        "contact_name": "Ana Ops",
    }
    data["fleet"]["aircraft"][0]["registration"] = "PK-RFX"
    data["network"]["airports"] = [{"icao": code, "alternates": []} for code in airports_list]
    data["assistant"] = (
        {"provider": "gemini", "model": "gemini-3.8-flash", "model_lite": "gemini-3.5-flash-lite"}
        if provider == "gemini"
        else {"provider": "ollama", "model": "gemma4:e4b", "model_lite": "gemma4:e4b"}
    )
    if feeds is not None:
        data["feeds"] |= feeds
    return AirlineAnswers.model_validate(data)


def wall() -> datetime:
    return timeutil.SystemClock().now()


@dataclass
class World:
    """The site's root store (metered as the demo), the meter, the access cache, and one
    space per airline (a store object per namespace)."""

    settings: Settings
    meter: StoreMeter
    root: MeteredStore
    access: AccessCache = field(default_factory=AccessCache)
    spaces: dict[str, TenantSpace] = field(default_factory=dict)

    def space(self, icao: str) -> TenantSpace:
        held = self.spaces.get(icao)
        if held is None:
            inner = open_store(self.settings, namespace=icao, shared=self.root)
            since = wall()
            held = self.spaces[icao] = TenantSpace(
                icao=icao,
                store=MeteredStore(inner, self.meter, icao, cache=TENANT_CACHED),
                feed_stats=FeedStats(since=since),
                conn_stats=ConnectionStats(since=since),
            )
        return held

    async def aclose(self) -> None:
        for held in self.spaces.values():
            await held.store.aclose()
        await self.root.aclose()


def world(tmp_path: Path, **overrides: Any) -> World:
    settings = site(tmp_path, **overrides)
    meter = StoreMeter(blob_puts_cap=settings.hosted_blob_puts_cap)
    return World(settings, meter, MeteredStore(open_store(settings), meter, "demo"))


async def airline_account(
    root: Any,
    icao: str = "RFB",
    *,
    email: str | None = None,
    verified: bool = True,
    hosting: bool = True,
    **answer_kw: Any,
) -> tuple[AirlineRecord, AirlineLogin]:
    """An airline account submitted and (by default) verified by an operator."""
    email = email or f"ana@{icao.lower()}.example"
    at = wall()
    record, login = await accounts.create_account(
        root, email=email, password_hash="scrypt$test", recovery_sha256="0" * 64, at=at
    )
    record = await accounts.submit(
        root, record.id, version=record.version, answers=answers(icao, **answer_kw), flags=[], at=at
    )
    if verified:
        stamp = Stamp(by=OPERATOR, at=at) if hosting else None
        record = await accounts.decide(
            root,
            record.id,
            version=record.version,
            actor=OPERATOR if hosting else "desk:Dee",
            verified=True,
            note=None,
            at=at,
            hosting=stamp,
        )
    return record, login


async def set_up(
    w: World, icao: str = "RFB", name: str = "Ana Ops", **kw: Any
) -> tuple[TenantRecord, Member, AirlineRecord, AirlineLogin]:
    record, login = await airline_account(w.root, icao, **kw)
    tenant, member = await tenants.set_up(
        w.root,
        record,
        login,
        name,
        space=w.space(icao),
        settings=w.settings,
        base_policy=base_policy(),
        airports=airports(),
        at=wall(),
    )
    return tenant, member, record, login


async def chain_of(w: World, icao: str) -> list[audit.ChainedAuditEntry]:
    held = w.space(icao)
    with held.bound():
        docs = await held.store.list_docs(
            Collection.AUDIT, limit=500, order_by="seq", descending=False
        )
    return [audit.ChainedAuditEntry.model_validate(doc) for doc in docs]


async def start(w: World, icao: str = "RFB", by: str = "Ana Ops#MB-0000000000") -> TenantRecord:
    return await tenants.start(
        w.root,
        icao,
        region="java_bali",
        by=by,
        max_slots=w.settings.hosted_max_tenants,
        space=w.space(icao),
        at=wall(),
    )


@contextmanager
def demo_on_replay_clock() -> Iterator[None]:
    """The demo's process clock set years back, as a REPLAY would."""
    with timeutil.use_clock(timeutil.FixedClock(datetime(2020, 1, 1, tzinfo=UTC))):
        yield


# --- set up -----------------------------------------------------------------------------


async def test_set_up_makes_the_record_the_first_ops_manager_and_policy_v1(tmp_path: Path) -> None:
    w = world(tmp_path)
    tenant, member, _record, login = await set_up(w)
    assert tenant.state == "setup"
    assert tenant.version == 1
    assert tenant.ops_managers == [member.id]
    assert member.role == "ops_manager"
    assert member.id.startswith("MB-")
    assert member.login_key == login.login_key
    assert tenant.region == "java_bali"
    assert tenant.assistant is not None
    assert tenant.assistant.model == "gemini-3.8-flash"
    stored = await tenants.get_tenant(w.root, "RFB")
    assert stored is not None
    assert stored.model_dump(mode="json") == tenant.model_dump(mode="json")
    with w.space("RFB").bound():
        v1 = await hosted_policy.get_version(w.space("RFB").store, 1)
    assert v1 is not None
    assert [c.name for c in v1.changes] == ["exposure.vertical_margin_ft"]
    entries = await chain_of(w, "RFB")
    assert [e.action for e in entries] == [AuditAction.HOSTED_SETUP]
    assert entries[0].actor == f"desk:Ana Ops#{member.id}"
    assert "@" not in json.dumps([e.model_dump(mode="json") for e in entries])
    await w.aclose()


async def test_an_ollama_assistant_is_not_carried_over(tmp_path: Path) -> None:
    w = world(tmp_path)
    tenant, *_ = await set_up(w, provider="ollama")
    assert tenant.assistant is None
    await w.aclose()


@pytest.mark.parametrize(
    ("verified", "hosting", "code"),
    [(False, True, "not_verified"), (True, False, "hosting_not_approved")],
)
async def test_set_up_needs_a_verified_airline_with_hosting_approved(
    tmp_path: Path, verified: bool, hosting: bool, code: str
) -> None:
    w = world(tmp_path)
    record, login = await airline_account(w.root, verified=verified, hosting=hosting)
    with pytest.raises(HostedRefused) as refused:
        await tenants.set_up(
            w.root,
            record,
            login,
            "Ana Ops",
            space=w.space("RFB"),
            settings=w.settings,
            base_policy=base_policy(),
            airports=airports(),
            at=wall(),
        )
    assert (refused.value.status, refused.value.code) == (409, code)
    assert await tenants.get_tenant(w.root, "RFB") is None
    await w.aclose()


async def test_set_up_twice_and_another_airline_on_the_same_icao_are_refused(
    tmp_path: Path,
) -> None:
    w = world(tmp_path)
    _, _, record, login = await set_up(w)
    with pytest.raises(HostedRefused, match="already_set_up"):
        await tenants.set_up(
            w.root,
            record,
            login,
            "Ana Ops",
            space=w.space("RFB"),
            settings=w.settings,
            base_policy=base_policy(),
            airports=airports(),
            at=wall(),
        )
    other, other_login = await airline_account(w.root, "RFB", email="eve@rfb2.example")
    with pytest.raises(HostedRefused, match="icao_taken"):
        await tenants.set_up(
            w.root,
            other,
            other_login,
            "Eve",
            space=w.space("RFB"),
            settings=w.settings,
            base_policy=base_policy(),
            airports=airports(),
            at=wall(),
        )
    await w.aclose()


async def test_a_display_name_follows_the_desk_rule(tmp_path: Path) -> None:
    assert tenants.display_name("  Ana   Ops ") == "Ana Ops"
    for bad in ("A", "x" * 33, "ana@rfb.example", "<b>"):
        with pytest.raises(HostedRefused, match="display_name"):
            tenants.display_name(bad)


# --- the states -------------------------------------------------------------------------


async def test_the_whole_life_of_an_airline(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, member, *_ = await set_up(w)
    by = tenants.member_by(member)
    space = w.space("RFB")
    shadow = await start(w, by=by)
    assert shadow.state == "shadow"
    assert shadow.started is not None
    assert (await tenants.slots(w.root)).holders == ["RFB"]
    with pytest.raises(HostedRefused, match="wrong_state"):
        await start(w, by=by)
    live = await tenants.go_live(w.root, "RFB", by=by, space=space, at=wall())
    assert live.state == "live"
    assert live.live is not None
    assert live.live.by == by
    back = await tenants.back_to_shadow(
        w.root, "RFB", by=by, reason="Rostering change", space=space, at=wall()
    )
    assert back.state == "shadow"
    assert back.live is None
    stopped = await tenants.stop_runs(
        w.root, "RFB", by=by, reason="Pause for the audit", space=space, at=wall()
    )
    assert stopped.state == "setup"
    assert (await tenants.slots(w.root)).holders == []
    await start(w, by=by)
    at = wall()
    suspended = await tenants.suspend(
        w.root, "RFB", by=OPERATOR, reason="Positions outside the fleet.", space=space, at=at
    )
    assert suspended.state == "suspended"
    assert (await tenants.slots(w.root)).holders == []
    with pytest.raises(HostedRefused, match="too_soon"):
        await tenants.mark_deleting(w.root, "RFB", by=OPERATOR, at=at + timedelta(days=6))
    resumed = await tenants.resume(w.root, "RFB", by=OPERATOR, max_slots=3, space=space, at=wall())
    assert resumed.state == "shadow"
    assert resumed.suspended is None
    assert resumed.started is not None
    assert tenants.shown_by(resumed.started.by) == "TEPHRA staff"
    assert tenants.shown_by("Ana Ops#MB-1a2b3c4d5e") == "Ana Ops"
    await tenants.suspend(w.root, "RFB", by=OPERATOR, reason="Again.", space=space, at=at)
    deleting = await tenants.mark_deleting(w.root, "RFB", by=OPERATOR, at=at + tenants.DELETE_AFTER)
    assert deleting.state == "deleting"
    assert deleting.model_key is None
    gone = await tenants.finish_delete(w.root, "RFB", at=wall())
    assert gone.state == "deleted"
    assert gone.deleted is not None
    assert gone.assistant is None
    actions = [e.action for e in await chain_of(w, "RFB")]
    assert actions == [
        AuditAction.HOSTED_SETUP,
        AuditAction.HOSTED_SHADOW,
        AuditAction.HOSTED_LIVE,
        AuditAction.HOSTED_SHADOW,
        AuditAction.HOSTED_STOPPED,
        AuditAction.HOSTED_SHADOW,
        AuditAction.HOSTED_SUSPENDED,
        AuditAction.HOSTED_RESUMED,
        AuditAction.HOSTED_SUSPENDED,
    ]
    suspend_note = (await chain_of(w, "RFB"))[6].note or ""
    assert "Its data can be deleted from" in suspend_note  # an operator's act, never automatic
    assert "unless resumed" not in suspend_note
    await w.aclose()


async def test_a_deleted_airline_may_be_set_up_again(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, _member, record, login = await set_up(w)
    at = wall() - timedelta(days=8)
    await tenants.suspend(w.root, "RFB", by=OPERATOR, reason="Test.", space=w.space("RFB"), at=at)
    await tenants.mark_deleting(w.root, "RFB", by=OPERATOR, at=wall())
    await tenants.finish_delete(w.root, "RFB", at=wall())
    again, _ = await tenants.set_up(
        w.root,
        record,
        login,
        "Ana Ops",
        space=w.space("RFB"),
        settings=w.settings,
        base_policy=base_policy(),
        airports=airports(),
        at=wall(),
    )
    assert again.state == "setup"
    await w.aclose()


async def test_four_starts_on_three_places_let_exactly_three_in(tmp_path: Path) -> None:
    w = world(tmp_path)
    codes = ["RFB", "RFC", "RFD", "RFE"]
    for code in codes:
        await set_up(w, code)
    results = await asyncio.gather(*(start(w, code) for code in codes), return_exceptions=True)
    refused = [r for r in results if isinstance(r, HostedRefused)]
    assert len(refused) == 1
    assert refused[0].code == "airline_limit_reached"
    assert len((await tenants.slots(w.root)).holders) == 3
    states = sorted([(await tenants.get_tenant(w.root, c)).state for c in codes])  # type: ignore[union-attr]
    assert states == ["setup", "shadow", "shadow", "shadow"]
    held = (await tenants.slots(w.root)).holders
    stopper = held[0]
    await tenants.stop_runs(
        w.root, stopper, by="Ana Ops#MB-0", reason="Make room", space=w.space(stopper), at=wall()
    )
    waiting = next(c for c in codes if c not in held)
    assert (await start(w, waiting)).state == "shadow"
    full = held[1]
    await tenants.suspend(w.root, full, by=OPERATOR, reason="Hold.", space=w.space(full), at=wall())
    await start(w, stopper)
    with pytest.raises(HostedRefused, match="airline_limit_reached"):
        await tenants.resume(w.root, full, by=OPERATOR, max_slots=3, space=w.space(full), at=wall())
    await w.aclose()


async def test_settings_changes_are_refused_while_suspended(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, member, *_ = await set_up(w)
    space = w.space("RFB")
    await tenants.suspend(w.root, "RFB", by=OPERATOR, reason="Hold.", space=space, at=wall())
    with pytest.raises(HostedRefused) as refused:
        await tenants.confirm_policy(
            w.root, "RFB", version=1, by=tenants.member_by(member), space=space, at=wall()
        )
    assert (refused.value.status, refused.value.code) == (403, "tenant_suspended")
    await w.aclose()


# --- policy versions on the record -------------------------------------------------------


async def test_a_new_policy_version_clears_the_confirmation(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, member, *_ = await set_up(w)
    by, space = tenants.member_by(member), w.space("RFB")
    confirmed = await tenants.confirm_policy(
        w.root, "RFB", version=1, by=by, space=space, at=wall()
    )
    assert confirmed.policy_confirmed is not None
    assert confirmed.policy_confirmed.version == 1
    from tephra.airline.models import PolicyChange

    change = PolicyChange(
        name="exposure.vertical_margin_ft", value=4000, reason="Company SOP 4.2 asks for it."
    )
    v2 = await tenants.set_policy_version(
        w.root,
        "RFB",
        [change],
        base_version=1,
        note=None,
        base_policy=base_policy(),
        by=by,
        space=space,
        at=wall(),
    )
    assert v2.policy_version == 2
    assert v2.policy_confirmed is None
    with pytest.raises(HostedRefused, match="version_conflict"):
        await tenants.set_policy_version(
            w.root,
            "RFB",
            [change],
            base_version=1,
            note=None,
            base_policy=base_policy(),
            by=by,
            space=space,
            at=wall(),
        )
    with pytest.raises(HostedRefused, match="version_conflict"):
        await tenants.confirm_policy(w.root, "RFB", version=1, by=by, space=space, at=wall())
    entry = (await chain_of(w, "RFB"))[-1]
    assert entry.action == AuditAction.POLICY_CHANGED
    assert entry.note == "Policy v2: exposure.vertical_margin_ft 3000 -> 4000"
    await w.aclose()


async def test_sra_acceptance_names_the_current_version_and_no_future_date(
    tmp_path: Path,
) -> None:
    w = world(tmp_path)
    _, member, *_ = await set_up(w)
    by, space, now = tenants.member_by(member), w.space("RFB"), wall()
    with pytest.raises(HostedRefused, match="future_date"):
        await tenants.record_sra(
            w.root,
            "RFB",
            version=1,
            accepted_by="Ana Ops, Head of Flight Ops",
            accepted_on=(now + timedelta(days=2)).date(),
            sra_ref=None,
            by=by,
            space=space,
            at=now,
        )
    with pytest.raises(HostedRefused, match="version_conflict"):
        await tenants.record_sra(
            w.root,
            "RFB",
            version=2,
            accepted_by="Ana Ops",
            accepted_on=now.date(),
            sra_ref=None,
            by=by,
            space=space,
            at=now,
        )
    recorded = await tenants.record_sra(
        w.root,
        "RFB",
        version=1,
        accepted_by="Ana Ops",
        accepted_on=now.date(),
        sra_ref="SRA-VA-2026-03",
        by=by,
        space=space,
        at=now,
    )
    assert recorded.sra is not None
    assert recorded.sra.sra_ref == "SRA-VA-2026-03"
    withdrawn = await tenants.withdraw_sra(
        w.root, "RFB", reason="Wrong version", by=by, space=space, at=now
    )
    assert withdrawn.sra is None
    await w.aclose()


async def test_restarts_are_counted_per_pacific_day(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    at = datetime(2026, 10, 17, 6, 0, tzinfo=UTC)
    assert await tenants.note_restart(w.root, "RFB", at=at) == 1
    assert await tenants.note_restart(w.root, "RFB", at=at) == 2
    assert await tenants.note_restart(w.root, "RFB", at=at + timedelta(hours=2)) == 1
    await w.aclose()


# --- wall clock and privacy -------------------------------------------------------------


async def test_entries_and_invites_carry_wall_time_while_the_demo_replays(
    tmp_path: Path,
) -> None:
    from tephra.hosted import members

    w = world(tmp_path)
    with demo_on_replay_clock():
        assert timeutil.now().year == 2020
        _, member, *_ = await set_up(w)
        made, _ = await members.invite(
            w.root,
            "RFB",
            "dee@rfb.example",
            "dispatcher",
            by=member,
            space=w.space("RFB"),
            at=wall(),
        )
        await tenants.suspend(
            w.root, "RFB", by=OPERATOR, reason="Hold.", space=w.space("RFB"), at=wall()
        )
    now = wall()
    for entry in await chain_of(w, "RFB"):
        assert abs((entry.at - now).total_seconds()) < 5
    assert abs((made.expires_at - members.INVITE_LIFE - now).total_seconds()) < 5
    await w.aclose()


async def test_the_demo_chain_never_gets_a_hosted_entry(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    await start(w)
    demo = await w.root.list_docs(Collection.AUDIT, limit=50)
    assert demo == []
    await w.aclose()


async def test_the_airline_store_refuses_work_outside_its_binding(tmp_path: Path) -> None:
    w = world(tmp_path)
    await set_up(w)
    with pytest.raises(RuntimeError, match="outside its binding"):
        await w.space("RFB").store.list_docs(Collection.AUDIT)
    await w.aclose()


# --- the workspace's view ---------------------------------------------------------------


async def test_hosted_me_says_what_the_login_may_do_next(tmp_path: Path) -> None:
    w = world(tmp_path)
    record, login = await airline_account(w.root, "RFB", hosting=False)
    me = await tenants.hosted_me(w.root, login, record, max_airlines=3)
    assert (me.can_set_up, me.waiting) == (None, "hosting_not_approved")
    record = await accounts.approve_hosting(
        w.root, record.id, by=OPERATOR, version=record.version, at=wall()
    )
    me = await tenants.hosted_me(w.root, login, record, max_airlines=3)
    assert me.can_set_up is not None
    assert me.can_set_up.icao == "RFB"
    assert me.waiting is None
    await tenants.set_up(
        w.root,
        record,
        login,
        "Ana Ops",
        space=w.space("RFB"),
        settings=w.settings,
        base_policy=base_policy(),
        airports=airports(),
        at=wall(),
    )
    me = await tenants.hosted_me(w.root, login, record, max_airlines=3)
    assert me.can_set_up is None
    assert [(m.icao, m.role, m.state) for m in me.memberships] == [("RFB", "ops_manager", "setup")]
    await w.aclose()
