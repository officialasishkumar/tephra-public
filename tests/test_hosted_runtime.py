"""A hosted airline's runtime beside the demo's in one process (SPEC-FINAL §2.3, §3.6, D12-D16,
D26): its own clock, settings, tenant, bus, ledger and model key; LIVE only; it follows the
demo runtime's retirement; and closing it leaves the shared source and its store open.

Offline: the stub model, fixture feeds, SQLite. Gemini backends are built (keys are fake) but no
model step runs on them: their agents are only constructed and inspected."""

import asyncio
import os
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr
from test_pipeline import AIRCRAFT, AT, DATA_DIR, POLICY, ROUTES, FixtureSource
from test_pipeline import make_runtime as make_demo_runtime
from test_pipeline import make_settings as make_demo_settings

from tephra import scheduler
from tephra.agents.adk_app import build_planner_agent
from tephra.agents.adk_runtime import AgentModelUnavailable, agent_model
from tephra.agents.ask import build_ask_agent
from tephra.agents.duty_officer import build_duty_agent
from tephra.agents.llm import GeminiBackend, UnavailableBackend, backend_for
from tephra.config import HOSTED_FEATURES, Settings, get_settings
from tephra.desk.approvals import list_advisories
from tephra.desk.failures import list_failures
from tephra.feeds import registry
from tephra.feeds.airports import load_airports
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import AdvisoryStatus, FeedId, FeedStatus, RunMode, TickReport
from tephra.pipeline import HostedModeLocked, HostedParts, Runtime, create_runtime
from tephra.recovery.agent import build_recovery_agent
from tephra.store.base import Collection
from tephra.store.metered import BLOB_PAUSED, MeteredStore, StoreMeter
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.events import get_bus
from tephra.util.scope import current_tenant
from tephra.util.timeutil import FixedClock, use_clock

RFB_HEX = "8a0b17"
"""Ring of Fire Charter's aircraft in the fixture: GIA417's track, flown as RFB417."""
NAMES: dict[str, tuple[str, str | None]] = {
    "RFB": ("Ring of Fire Charter", "RB"),
    "RFC": ("Ring of Fire Cargo", None),
}
REPLAY_AT = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)
"""The demo's process clock in these tests: a replay's recorded time, far from the wall."""
KEY_RFB = "AIzaRFB-test-key-0123456789abcdefghijklmn"
KEY_RFC = "AIzaRFC-test-key-0123456789abcdefghijklmn"


def rfb_aircraft(callsign: str = "RFB417") -> list[dict[str, Any]]:
    return [{**AIRCRAFT[0], "hex": RFB_HEX, "flight": f"{callsign:<8}"}, *AIRCRAFT[1:]]


def hosted_settings(
    tmp_path: Path, icao: str = "RFB", *, stage: str = "shadow", **changes: Any
) -> Settings:
    name, iata = NAMES[icao]
    values: dict[str, Any] = {
        "llm": "stub",
        "store": "sqlite",
        "sqlite_path": tmp_path / "tenants" / f"{icao}.sqlite3",
        "cache_dir": tmp_path / "cache",
        "data_dir": DATA_DIR,
        "features": HOSTED_FEATURES,
        "recovery_auto": False,
        "science": False,
        "visitor_access": "off",
        "fleet_prefixes": icao,
        "airline_name": name,
        "airline_icao": icao,
        "airline_iata": iata,
        "hosted_tenant": icao,
        "hosted_stage": stage,
        "tick_deadline_s": 25,
        **changes,
    }
    return Settings(_env_file=None, **values)


async def hosted_runtime(
    tmp_path: Path,
    meter: StoreMeter,
    *,
    icao: str = "RFB",
    settings: Settings | None = None,
    source: Any = None,
    fence: Callable[[], bool] = lambda: False,
    unavailable: str | None = None,
) -> Runtime:
    settings = settings or hosted_settings(tmp_path, icao)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    store = MeteredStore(
        SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs"), meter, icao
    )
    parts = HostedParts(
        tenant=icao,
        store=store,
        source=source if source is not None else FixtureSource(rfb_aircraft()),
        catalogue=load_volcanoes(DATA_DIR),
        airports=load_airports(DATA_DIR, min_runway_m=POLICY.alternates.min_runway_m.value),
        routes=ROUTES,
        policy=POLICY,
        own_schedule=None,
        llm_unavailable=unavailable,
        fence=fence,
    )
    return await create_runtime(settings, hosted=parts)


async def tick_and_drain(runtime: Runtime) -> TickReport:
    report = await runtime.tick(reason="manual")
    with runtime.bound():
        await runtime.worker.drain()
    return report


@pytest.fixture
def meter() -> StoreMeter:
    return StoreMeter(blob_puts_cap=4_000)


class Seen:
    """What a probe saw: (where, now, tenant, airline code in the bound settings)."""

    def __init__(self) -> None:
        self.rows: list[tuple[str, datetime, str | None, str | None]] = []

    def note(self, where: str) -> None:
        self.rows.append((where, timeutil.now(), current_tenant(), get_settings().hosted_tenant))


# --- context: clock, settings and tenant ---------------------------------------------------


async def test_two_airlines_and_a_replaying_demo_each_keep_their_own_clock(
    tmp_path: Path, meter: StoreMeter, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = Seen()
    monkeypatch.setattr(
        scheduler,
        "_adsb_passes",
        lambda runtime, started, offsets: _probe(seen, f"adsb {runtime.hosted}"),
    )
    with use_clock(FixedClock(REPLAY_AT)):
        demo = make_demo_runtime(make_demo_settings(tmp_path / "demo"), FixtureSource())
        rfb = await hosted_runtime(tmp_path, meter, icao="RFB")
        rfc = await hosted_runtime(tmp_path, meter, icao="RFC")
        try:
            for runtime in (rfb, rfc):
                runtime.analyse = _noting(seen, f"tick {runtime.hosted}", runtime.analyse)
                runtime.worker.work_once = _noting(  # type: ignore[method-assign]
                    seen, f"worker {runtime.hosted}", _no_work
                )
                await runtime.tick(reason="hosted")
                runtime.start_worker()
                runtime.worker.wake()
                runtime.spawn(_probe(seen, f"task {runtime.hosted}"))
            demo.spawn(_probe(seen, "task demo"))
            for _ in range(20):
                await asyncio.sleep(0.01)
            wall = timeutil.SystemClock().now()
            demo_now = timeutil.now()
        finally:
            for runtime in (rfb, rfc, demo):
                await runtime.aclose()

    where = {row[0] for row in seen.rows}
    for icao in ("RFB", "RFC"):
        assert {f"tick {icao}", f"adsb {icao}", f"worker {icao}", f"task {icao}"} <= where
    assert demo_now == REPLAY_AT
    for name, at, tenant, settings_tenant in seen.rows:
        if name == "task demo":
            assert (at, tenant, settings_tenant) == (REPLAY_AT, None, None)
            continue
        icao = name.split()[-1]
        assert abs((wall - at).total_seconds()) < 60, name
        assert (tenant, settings_tenant) == (icao, icao), name


async def _probe(seen: Seen, where: str) -> None:
    seen.note(where)


async def _no_work(*args: Any) -> bool:
    return False


def _noting(seen: Seen, where: str, inner: Callable[..., Any]) -> Callable[..., Any]:
    async def noted(*args: Any, **kwargs: Any) -> Any:
        seen.note(where)
        return await inner(*args, **kwargs)

    return noted


async def test_the_airline_store_refuses_use_outside_the_runtime_binding(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    try:
        with pytest.raises(RuntimeError, match="outside its binding"):
            await rfb.store.get(Collection.RUNTIME, "state")
        with rfb.bound():
            assert await rfb.store.get(Collection.RUNTIME, "state") is None
            with pytest.raises(RuntimeError, match="set_clock inside a bound clock"):
                timeutil.set_clock(FixedClock(REPLAY_AT))
    finally:
        await rfb.aclose()


async def test_a_hosted_runtime_has_its_own_bus_and_never_switches_mode(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    try:
        assert rfb.bus is not get_bus()
        assert rfb.mode is RunMode.LIVE
        with pytest.raises(HostedModeLocked):
            await rfb.switch_mode(RunMode.REPLAY)
        with pytest.raises(HostedModeLocked):
            await rfb._switch(RunMode.REPLAY, auto=True)
        assert rfb.mode is RunMode.LIVE
    finally:
        await rfb.aclose()


async def test_hosted_settings_must_be_the_airlines_own_live_settings(
    tmp_path: Path, meter: StoreMeter
) -> None:
    other = hosted_settings(tmp_path, "RFC")
    with pytest.raises(ValueError, match="not RFB's hosted LIVE settings"):
        await hosted_runtime(tmp_path, meter, icao="RFB", settings=other)


# --- keys (B1) -----------------------------------------------------------------------------


def _agents(runtime: Runtime) -> list[Any]:
    """Every ADK agent the runtime builds: planner, Coordinator, Ask, recovery."""
    model = agent_model(runtime.settings, runtime.llm)
    return [
        build_planner_agent(model),
        build_duty_agent(model, toolkit=None),  # type: ignore[arg-type]
        build_ask_agent(model, SimpleNamespace(tools=list)),  # type: ignore[arg-type]
        build_recovery_agent(model, box=None),  # type: ignore[arg-type]
    ]


async def test_each_airlines_agents_carry_its_own_key_and_the_environment_is_untouched(
    tmp_path: Path, meter: StoreMeter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "process-key-must-stay")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    before = dict(os.environ)
    runtimes = {
        icao: await hosted_runtime(
            tmp_path,
            meter,
            icao=icao,
            settings=hosted_settings(tmp_path, icao, llm="gemini", gemini_api_key=key),
        )
        for icao, key in (("RFB", KEY_RFB), ("RFC", KEY_RFC))
    }
    try:
        assert dict(os.environ) == before
        for icao, key in (("RFB", KEY_RFB), ("RFC", KEY_RFC)):
            runtime = runtimes[icao]
            assert isinstance(runtime.llm, GeminiBackend)
            for agent in _agents(runtime):
                assert type(agent.model).__name__ == "Gemini"
                assert agent.model.client_kwargs == {"api_key": key, "vertexai": False}
                assert key not in repr(agent.model)
                assert key[:8] not in agent.model.model_dump_json()
            assert key not in repr(runtime.settings)
    finally:
        for runtime in runtimes.values():
            await runtime.aclose()


async def test_an_airline_without_a_usable_key_gets_ai_unavailable_and_no_stand_in(
    tmp_path: Path, meter: StoreMeter
) -> None:
    reason = "no model key is set"
    settings = hosted_settings(tmp_path, llm="gemini")
    rfb = await hosted_runtime(tmp_path, meter, settings=settings, unavailable=reason)
    rfb.wall_clock = FixedClock(AT)
    try:
        assert isinstance(rfb.llm, UnavailableBackend)
        assert rfb.llm.name == "gemini"
        assert rfb.llm.metered
        assert await rfb.llm.reserve("lite") == reason
        # the pages read the airline's state from the budget: "AI unavailable" and why, never "on"
        assert (await rfb.budget_view()).unavailable == reason
        await tick_and_drain(rfb)
        with rfb.bound():
            drafts = await list_advisories(rfb.store, status=AdvisoryStatus.DRAFT, limit=50)
            failures = await list_failures(rfb.store, replay=False)
    finally:
        await rfb.aclose()

    assert any(f.hex == RFB_HEX for f in rfb.exposed.values()), "the flight is exposed"
    assert drafts == [], "nothing is drafted in a model's place"
    assert failures, "the flight goes to the Desk as AI UNAVAILABLE"
    assert all(reason in failure.reason for failure in failures)


# --- what a hosted airline does not run -----------------------------------------------------


async def test_recovery_is_not_built_for_a_real_airlines_network(
    tmp_path: Path, meter: StoreMeter
) -> None:
    settings = hosted_settings(tmp_path, recovery_auto=True)
    rfb = await hosted_runtime(tmp_path, meter, settings=settings)
    rfb.wall_clock = FixedClock(AT)
    try:
        await rfb.tick(reason="manual")
        report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="manual")
        assert rfb.recovery_due is None
        assert rfb.start_recovery(report) == {"error": "NOT BUILT FOR YOUR NETWORK"}
        with rfb.bound():
            await rfb.recover_queued(["WARA"])
        assert not rfb.worker.recovery_queued()
    finally:
        await rfb.aclose()


async def test_the_hosted_map_draws_the_airlines_own_fleet_only(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    rfb.wall_clock = FixedClock(AT)
    try:
        await rfb.tick(reason="manual")
        with rfb.bound():
            wall = await rfb.wall_snapshot()
    finally:
        await rfb.aclose()
    drawn = {feature["properties"]["hex"] for feature in wall.aircraft["features"]}
    assert drawn == {RFB_HEX}
    assert len(rfb.aircraft()) == len(AIRCRAFT), "every aircraft is still seen"


# --- rollouts: the fence -------------------------------------------------------------------


async def test_a_hosted_runtime_retires_with_the_demo_runtime(
    tmp_path: Path, meter: StoreMeter
) -> None:
    demo = SimpleNamespace(retired=False)
    rfb = await hosted_runtime(tmp_path, meter, fence=lambda: demo.retired)
    rfb.wall_clock = FixedClock(AT)
    try:
        await rfb.tick(reason="manual")
        assert not rfb.retired
        demo.retired = True
        assert rfb.retired
        with rfb.bound():
            assert await rfb.check_writer()
            report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="t")
            assert await rfb.worker.work_once(report) is False
            writes = meter.day().writes.get("RFB", 0)
            await rfb.checkpoint(force=True)
        assert meter.day().writes.get("RFB", 0) == writes, "a retired airline writes nothing"
    finally:
        await rfb.aclose()


async def test_a_hosted_runtime_claims_no_writer(tmp_path: Path, meter: StoreMeter) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    try:
        with rfb.bound():
            await rfb.claim_writer()
            assert await rfb.store.get(Collection.RUNTIME, "writer") is None
            assert await rfb.check_writer() is False
    finally:
        await rfb.aclose()


# --- changes without a restart (D26) --------------------------------------------------------


async def test_set_policy_changes_the_summary(tmp_path: Path, meter: StoreMeter) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    try:
        renamed = POLICY.model_copy(update={"policy_id": "RFB-POLICY-A", "version": "RFB-2"})
        await rfb.set_policy(renamed)
        assert (rfb.policy_summary.policy_id, rfb.policy_summary.version) == (
            "RFB-POLICY-A",
            "RFB-2",
        )
    finally:
        await rfb.aclose()


async def test_reconfigure_reaches_running_tasks_and_new_drafts_only(
    tmp_path: Path, meter: StoreMeter
) -> None:
    rfb = await hosted_runtime(tmp_path, meter)
    rfb.wall_clock = FixedClock(AT)
    seen: list[str | None] = []
    go = asyncio.Event()

    async def worker_like() -> None:
        seen.append(get_settings().hosted_stage)
        await go.wait()
        seen.append(get_settings().hosted_stage)

    try:
        await tick_and_drain(rfb)
        with rfb.bound():
            shadow_drafts = await list_advisories(rfb.store, limit=50)
        assert shadow_drafts
        assert all(draft.shadow for draft in shadow_drafts)
        task = rfb.spawn(worker_like())
        await asyncio.sleep(0)
        await rfb.reconfigure(rfb.settings.model_copy(update={"hosted_stage": "live"}))
        go.set()
        await task
        assert seen == ["shadow", "live"]
        assert not rfb.airline.shadow
        with rfb.bound():
            kept = await list_advisories(rfb.store, limit=50)
        assert {d.id for d in kept if d.shadow} >= {d.id for d in shadow_drafts}
    finally:
        await rfb.aclose()


async def test_reconfigure_refuses_other_settings_and_a_key_without_its_backend(
    tmp_path: Path, meter: StoreMeter
) -> None:
    settings = hosted_settings(tmp_path, llm="gemini", gemini_api_key=KEY_RFB)
    rfb = await hosted_runtime(tmp_path, meter, settings=settings)
    try:
        with pytest.raises(ValueError, match="cannot change region"):
            await rfb.reconfigure(settings.model_copy(update={"region": "kyushu"}))
        rotated = settings.model_copy(update={"gemini_api_key": SecretStr(KEY_RFC)})
        with pytest.raises(ValueError, match="needs its backend"):
            await rfb.reconfigure(rotated)
        await rfb.reconfigure(rotated, llm=backend_for(rotated, unavailable=None, quota=rfb.quota))
        for agent in _agents(rfb):
            assert agent.model.client_kwargs["api_key"] == KEY_RFC
        await rfb.reconfigure(
            rotated.model_copy(update={"ai_interactive_share": 0.3}),
            llm=backend_for(rotated, unavailable="no model key is set", quota=rfb.quota),
        )
        assert rfb.quota.shares(rotated.model_lite) is not None
        with pytest.raises(AgentModelUnavailable, match="no model key is set"):
            agent_model(rfb.settings, rfb.llm)
        assert (await rfb.budget_view()).unavailable == "no model key is set"
        await rfb.reconfigure(rotated, llm=backend_for(rotated, unavailable=None, quota=rfb.quota))
        assert (await rfb.budget_view()).unavailable is None
    finally:
        await rfb.aclose()


# --- closing ---------------------------------------------------------------------------------


class SpySource(FixtureSource):
    def __init__(self, aircraft: Sequence[Any]) -> None:
        super().__init__(aircraft)
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


async def test_aclose_leaves_the_shared_source_and_the_store_open(
    tmp_path: Path, meter: StoreMeter
) -> None:
    source = SpySource(rfb_aircraft())
    rfb = await hosted_runtime(tmp_path, meter, source=source)
    rfb.wall_clock = FixedClock(AT)
    await rfb.tick(reason="manual")
    await rfb.aclose()

    assert source.closed is False
    with rfb.bound():
        assert await rfb.store.get(Collection.RUNTIME, "state") is not None, "checkpointed"
    await rfb.store.aclose()


# --- frames past the month's storage operations (D20) ---------------------------------------


async def test_frames_past_the_months_uploads_are_paused_and_said_never_stood_in_for(
    tmp_path: Path,
) -> None:
    used_up = StoreMeter(blob_puts_cap=0)
    rfb = await hosted_runtime(tmp_path, used_up)
    rfb.wall_clock = FixedClock(AT)
    try:
        await rfb.tick(reason="manual")
        assert rfb.live.active
        with rfb.bound():
            polled = await registry.poll(FeedId.FRAMES, rfb)
    finally:
        await rfb.aclose()
    health = rfb.live.health[FeedId.FRAMES]
    assert polled.ok is False
    assert polled.error == BLOB_PAUSED
    assert (health.status, health.last_error) == (FeedStatus.DISABLED, BLOB_PAUSED)
    assert rfb.live.frames == {}, "no frame is drawn that was not stored"


# --- the local scheduler's hook for the hosted pass -----------------------------------------


async def test_the_local_scheduler_calls_after_tick_once_per_tick() -> None:
    stop = asyncio.Event()
    kicks: list[str] = []

    class Ticking:
        settings = SimpleNamespace(tick_interval_s=0.01)

        async def tick(self, *, reason: str) -> None:
            kicks.append(f"tick {reason}")
            if reason == "local":
                stop.set()

    def after_tick() -> None:
        kicks.append("kick")
        raise RuntimeError("a failing hook does not stop the demo's ticks")

    await scheduler.run_local_scheduler(Ticking(), stop, after_tick=after_tick)  # type: ignore[arg-type]
    assert kicks == ["tick startup", "kick", "tick local", "kick"]
