"""The access cache (F12, S7, S12): found and not-found entries for 10 minutes, a drop takes
effect on the next lookup, ``generation`` moves, roles follow the record's ops managers."""

from pathlib import Path

from tephra.airline import sessions
from tephra.hosted.access import AccessCache, effective
from tephra.hosted.models import Operator
from tephra.store.base import Collection
from tests.test_hosted_tenants import set_up, wall, world


class Ticks:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_a_member_is_read_once_then_held(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, ana, _, login = await set_up(w)
    cache = AccessCache()
    assert not cache.holds_member(login.login_key, "RFB")
    found = await cache.member(w.root, login.login_key, login.session_version, "RFB")
    assert found is not None
    assert found.id == ana.id
    assert cache.holds_member(login.login_key, "RFB")
    reads = sum(w.meter.day().reads.values())
    again = await cache.member(w.root, login.login_key, login.session_version, "RFB")
    assert again is not None
    assert again.id == ana.id
    assert sum(w.meter.day().reads.values()) == reads
    await w.aclose()


async def test_an_old_cookie_version_and_a_stranger_get_nothing(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, _, _, login = await set_up(w)
    cache = AccessCache()
    assert await cache.member(w.root, login.login_key, login.session_version + 1, "RFB") is None
    assert await cache.member(w.root, login.login_key, login.session_version, "RFC") is None
    reads = sum(w.meter.day().reads.values())
    assert await cache.member(w.root, login.login_key, login.session_version, "RFC") is None
    assert sum(w.meter.day().reads.values()) == reads
    await w.aclose()


async def test_a_drop_takes_effect_on_the_next_lookup(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, _, _, login = await set_up(w)
    cache = AccessCache()
    await cache.member(w.root, login.login_key, login.session_version, "RFB")
    generation = cache.generation
    await sessions.sign_out_everywhere(w.root, login.login_key, access=cache)
    assert cache.generation == generation + 1
    assert not cache.holds_member(login.login_key, "RFB")
    assert await cache.member(w.root, login.login_key, login.session_version, "RFB") is None
    await w.aclose()


async def test_drop_by_airline_leaves_other_airlines(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, _, _, login = await set_up(w)
    cache = AccessCache()
    await cache.member(w.root, login.login_key, 1, "RFB")
    await cache.member(w.root, login.login_key, 1, "RFC")
    cache.drop(icao="RFC")
    assert cache.holds_member(login.login_key, "RFB")
    assert not cache.holds_member(login.login_key, "RFC")
    cache.drop()
    assert not cache.holds_member(login.login_key, "RFB")
    await w.aclose()


async def test_entries_expire_after_ten_minutes(tmp_path: Path) -> None:
    w = world(tmp_path)
    _, _, _, login = await set_up(w)
    ticks = Ticks()
    cache = AccessCache(clock=ticks)
    await cache.member(w.root, login.login_key, 1, "RFB")
    ticks.now += 599
    assert cache.holds_member(login.login_key, "RFB")
    ticks.now += 2
    assert not cache.holds_member(login.login_key, "RFB")
    await w.aclose()


async def test_the_role_follows_the_records_ops_managers(tmp_path: Path) -> None:
    w = world(tmp_path)
    tenant, ana, _, login = await set_up(w)
    demoted = tenant.model_copy(update={"ops_managers": ["MB-ffffffffff"]})
    cache = AccessCache()
    seen = await cache.member(w.root, login.login_key, 1, "RFB", record=demoted)
    assert seen is not None
    assert seen.role == "dispatcher"
    assert effective(ana.model_copy(update={"role": "viewer"}), tenant).role == "ops_manager"
    await w.aclose()


async def test_an_operator_is_refused_once_disabled_or_signed_out(tmp_path: Path) -> None:
    w = world(tmp_path)
    op = Operator(
        login_key="k" * 64,
        email="m.tan@tephra.example",
        name="M. Tan",
        password="scrypt$test",
        created_at=wall(),
    )
    await w.root.put(Collection.OPERATORS, op.login_key, op.model_dump(mode="json"))
    cache = AccessCache()
    seen = await cache.operator(w.root, op.login_key, 1)
    assert seen is not None
    assert seen.login_key == op.login_key
    assert await cache.operator(w.root, op.login_key, 2) is None
    from tephra.airline.models import Stamp

    off = op.model_copy(update={"disabled": Stamp(by="operator:R. Osei#9a0b7c6d", at=wall())})
    await w.root.put(Collection.OPERATORS, op.login_key, off.model_dump(mode="json"))
    assert await cache.operator(w.root, op.login_key, 1) is not None
    cache.drop(login_key=op.login_key)
    assert await cache.operator(w.root, op.login_key, 1) is None
    await w.aclose()
