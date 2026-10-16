"""Airline data connections: the push format, keys, the push API and the sample feed (the Connect
page folded into onboarding: ``/connect`` redirects)."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from shapely.geometry import box
from test_pipeline import AT, FixtureSource, make_runtime, make_settings

from tephra.api.server import create_app
from tephra.config import PROJECT_ROOT
from tephra.desk import connections, sample_feed
from tephra.models import AIRLINE_FORMAT, POSITIONS_FORMAT, AuditAction, Connection, SseEvent
from tephra.store.base import Collection
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

PIN = "4321"
DATA = PROJECT_ROOT / "data"


def position(**changes: Any) -> dict[str, Any]:
    return {
        "hex": "8A0A1E",
        "callsign": "btk6711",
        "type_icao": "A320",
        "lat": -5.26,
        "lon": 105.79,
        "alt_baro_ft": 14425,
        "gs_kt": 393.0,
        "track_deg": 89.6,
        "observed_at": timeutil.to_iso(AT - timedelta(seconds=20)),
        **changes,
    }


def connection() -> Connection:
    return Connection(
        id="CN-0123456789",
        name="Test airline",
        created_at=AT,
        created_by="desk:Ana K",
        key_sha256="0" * 64,
        key_hint="abcd",
    )


def test_a_push_is_checked_record_by_record() -> None:
    raw = [
        position(),
        position(hex="zz0000"),
        position(observed_at=timeutil.to_iso(AT - timedelta(hours=2))),
        position(lat=95),
    ]
    accepted, problems = connections.checked_positions(raw, connection(), AT)

    assert [(a.hex, a.callsign) for a in accepted] == [("8a0a1e", "BTK6711")]
    assert accepted[0].source_id.startswith("PUSH:CN-0123456789:")
    assert [p.index for p in problems] == [1, 2, 3]
    assert problems[0].reason.startswith("hex:")
    assert "not within 5 min of TEPHRA's clock" in problems[1].reason


async def test_pushed_positions_join_the_aircraft_and_say_so(tmp_path: Path) -> None:
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            made, key = await connections.create_connection(
                runtime.store, "RFA ops", actor="desk:A"
            )
            assert await connections.find_by_key(runtime.store, key) == made
            result = await runtime.take_push(made, [position(), position(hex="nothex")])
            aircraft = runtime.aircraft()
            [summary] = [e.data for e in runtime.bus.recent(SseEvent.PUSH, limit=5)]
            stored = Connection.model_validate(
                await runtime.store.get(Collection.CONNECTIONS, made.id)
            )
            await connections.revoke_connection(runtime.store, made.id, actor="desk:A")
            revoked = await connections.find_by_key(runtime.store, key)
            actions = [doc["action"] for doc in await runtime.store.list_docs(Collection.AUDIT)]
        finally:
            await runtime.aclose()

    assert (result.accepted, [p.index for p in result.rejected]) == (1, [1])
    assert [a.hex for a in aircraft if a.source_id.startswith("PUSH:")] == ["8a0a1e"]
    assert (summary["accepted"], summary["rejected"], summary["name"]) == (1, 1, "RFA ops")
    assert (stored.pushes, stored.accepted, stored.rejected) == (1, 1, 1)
    assert stored.key_sha256 != key
    assert key not in stored.model_dump_json()
    assert revoked is None
    assert AuditAction.CONNECTION_CREATED in actions
    assert AuditAction.CONNECTION_REVOKED in actions


async def test_an_old_push_drops_off_the_map(tmp_path: Path) -> None:
    clock = FixedClock(AT)
    with use_clock(clock):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            await runtime.take_push(connection(), [position()])
            now = len(runtime.aircraft())
            clock.advance(timedelta(seconds=connections.PUSH_FRESH_S + 60))
            later = len(runtime.aircraft())
        finally:
            await runtime.aclose()
    assert (now, later) == (1, 0)


def test_the_sample_flights_are_real_recorded_fixes_that_move() -> None:
    from tephra.config import Settings

    pool = sample_feed.load_pool(DATA, Settings(_env_file=None).region_preset.bbox)
    assert len(pool) > 100
    flight = pool[0]
    [start] = sample_feed.positions_at([replace(flight, phase=0.0)], 0.0, AT)
    [later] = sample_feed.positions_at([replace(flight, phase=0.0)], 600.0, AT)
    assert (start["hex"], start["callsign"]) == (flight.hex, flight.callsign)
    assert (start["lat"], start["lon"]) == (round(flight.lat, 5), round(flight.lon, 5))
    assert (later["lat"], later["lon"]) != (start["lat"], start["lon"])
    assert later["alt_baro_ft"] == flight.alt_baro_ft


def test_the_sample_feed_picks_flights_that_cross_the_ash_first() -> None:
    from tephra.config import Settings

    pool = sample_feed.load_pool(DATA, Settings(_env_file=None).region_preset.bbox)
    area = box(105.0, -7.5, 107.5, -5.0)
    picked = sample_feed.pick_flights(pool, [area], skip=set(), limit=12)
    assert len(picked) == 12
    assert all(f.leg().intersects(area) for f in picked[:8])


@pytest.fixture
def client(tmp_path: Path) -> Any:
    settings = make_settings(
        tmp_path,
        desk_pin=SecretStr(PIN),
        session_secret=SecretStr("test-session-secret-0123456789abcdef"),
        local_scheduler=False,
    )
    with use_clock(FixedClock(AT)), TestClient(create_app(settings)) as test_client:
        yield test_client


def test_the_connect_api_end_to_end(client: TestClient) -> None:
    fmt = client.get("/api/connect/format").json()
    assert fmt["format"] == AIRLINE_FORMAT
    assert fmt["schema"]["properties"]["format"] == {"enum": [AIRLINE_FORMAT, POSITIONS_FORMAT]}
    assert set(fmt["schema"]["properties"]) == {
        "format",
        "positions",
        "flight_plans",
        "pilot_reports",
    }
    sample = client.get("/api/connect/sample.json")
    assert "attachment" in sample.headers["content-disposition"]
    assert sample.json()["format"] == AIRLINE_FORMAT
    assert sample.json()["positions"]
    page = client.get("/connect", follow_redirects=False)
    assert (page.status_code, page.headers["location"]) == (307, "/onboard")

    assert client.get("/api/desk/connections").status_code == 401
    login = client.post("/api/desk/login", json={"name": "Ana K", "pin": PIN})
    assert login.status_code == 200
    made = client.post("/api/desk/connections", json={"name": "RFA ops"}).json()
    key = made["key"]
    assert key.startswith(connections.KEY_PREFIX)
    listed = client.get("/api/desk/connections").json()
    assert [c["id"] for c in listed["connections"]] == [made["id"]]
    assert all(c["key"] is None for c in listed["connections"])

    batch = {"format": POSITIONS_FORMAT, "positions": [position(), position(lat="north")]}
    assert client.post("/api/push/positions", json=batch).status_code == 401
    pushed = client.post(
        "/api/push/positions", json=batch, headers={"Authorization": f"Bearer {key}"}
    )
    assert pushed.status_code == 200
    assert pushed.json()["accepted"] == 1
    assert [p["index"] for p in pushed.json()["rejected"]] == [1]
    again = client.post(
        "/api/push/positions", json=batch, headers={"Authorization": f"Bearer {key}"}
    )
    assert again.status_code == 429

    live = client.get("/api/connect/live").json()
    assert [d["hex"] for d in live["dots"]] == ["8a0a1e"]
    assert [f["per_min"] for f in live["flows"]] == [1]
    assert live["recent"][0]["accepted"] == 1
    old = position(observed_at=timeutil.to_iso(AT - timedelta(days=3)))
    stamped = client.post(
        "/api/desk/upload", json={"format": POSITIONS_FORMAT, "positions": [old], "retime": True}
    )
    kept_old = client.post(
        "/api/desk/upload", json={"format": POSITIONS_FORMAT, "positions": [old], "retime": False}
    )
    assert stamped.json()["accepted"] == 1
    assert kept_old.json()["accepted"] == 0
    names = [c["name"] for c in client.get("/api/desk/connections").json()["connections"]]
    assert names.count("Uploaded files") == 1

    client.post(f"/api/desk/connections/{made['id']}/revoke", json={})
    gone = client.post(
        "/api/push/positions", json=batch, headers={"Authorization": f"Bearer {key}"}
    )
    assert gone.status_code == 401


async def test_the_sample_feed_starts_and_stops(tmp_path: Path) -> None:
    runtime = make_runtime(make_settings(tmp_path, data_dir=DATA), FixtureSource())
    try:
        sample = await runtime.start_sample_feed(actor="desk:A")
        again = await runtime.start_sample_feed(actor="desk:A")
        await asyncio.sleep(0.3)
        running = runtime.sample_stop is not None
        runtime.stop_sample_feed()
        pushed = Connection.model_validate(
            await runtime.store.get(Collection.CONNECTIONS, sample.id)
        )
    finally:
        await runtime.aclose()
    assert sample.sample
    assert again.id == sample.id
    assert running
    assert runtime.sample_stop is None
    assert pushed.pushes >= 1


def plan(**changes: Any) -> dict[str, Any]:
    return {
        "flight": "RFA4259",
        "hex": "8a0a1e",
        "callsign": "BTK6711",
        "origin_icao": "WIII",
        "dest_icao": "WADD",
        "cruise_fl": 340,
        **changes,
    }


async def test_a_flight_plan_gives_its_flight_the_airlines_route(tmp_path: Path) -> None:
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            result = await runtime.take_push(
                connection(),
                [position(track_deg=110.0, lat=-6.3, lon=107.5)],
                plans=[plan(), plan(dest_icao="WIII"), plan(hex=None, callsign=None)],
            )
            routes = runtime.known_routes()
            numbers = runtime.plan_numbers()
            lines = runtime.plan_lines()
        finally:
            await runtime.aclose()

    assert result.plans_taken == 1
    assert [(p.section, p.index) for p in result.rejected] == [
        ("flight_plans", 1),
        ("flight_plans", 2),
    ]
    route = routes["8a0a1e"]
    assert (route.origin_icao, route.dest_icao, route.source) == ("WIII", "WADD", "airline-plan")
    assert numbers == {"8a0a1e": "RFA4259"}
    assert [(line.flight, line.closed) for line in lines] == [("RFA4259", False)]


async def test_a_pushed_pilot_report_is_entered_as_a_crew_report(tmp_path: Path) -> None:
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            await runtime.take_push(connection(), [position()])
            report = {
                "hex": "8a0a1e",
                "cues": ["ASH_SEEN"],
                "level_from_fl": 120,
                "level_to_fl": 160,
                "observed_at": timeutil.to_iso(AT - timedelta(seconds=10)),
            }
            first = await runtime.take_push(connection(), reports=[report, {"hex": "8a0a1e"}])
            again = await runtime.take_push(connection(), reports=[report])
            stored = await runtime.store.list_docs(Collection.CREW_REPORTS)
        finally:
            await runtime.aclose()

    assert first.reports_taken == 1
    assert [(p.section, p.index) for p in first.rejected] == [("pilot_reports", 1)]
    assert again.reports_taken == 1
    assert len(stored) == 1
    assert stored[0]["entered_by"].startswith("connect:")
