"""The own-fleet filter and the own-airport closure check of an airline's own TEPHRA: empty by
default, so the demo's exposure, closures and ``/api/state`` stay exactly as they were."""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_pipeline import (
    AT,
    GIA417,
    SEMERU,
    FixtureSource,
    make_runtime,
    make_settings,
    tick_and_work,
)

from tephra.api import server
from tephra.config import Settings
from tephra.desk.approvals import list_advisories
from tephra.geo.fleet import ALL_AIRCRAFT, FleetFilter
from tephra.models import Aircraft, Connection, OwnFleet
from tephra.pipeline import Runtime
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

PUSHED_HEX = "8a0999"
CLOSED = "WARA"
"""The catalogue airport the fixture case's Semeru area closes (code only)."""


def target(**changes: Any) -> Aircraft:
    return Aircraft(
        **{
            "hex": "8a0a1e",
            "callsign": "RFA417",
            "lat": -8.15,
            "lon": 113.7,
            "alt_baro_ft": 12000,
            "observed_at": AT,
            "source_id": "adsb.lol:point:x",
            **changes,
        }
    )


def pushed_position(**changes: Any) -> dict[str, Any]:
    """A position in the Semeru area on the fixture's track, pushed by the airline."""
    return {
        "hex": PUSHED_HEX,
        "callsign": "RFB6711",
        "type_icao": "A320",
        "lat": -8.15,
        "lon": 113.70,
        "alt_baro_ft": 12000,
        "gs_kt": 420.0,
        "track_deg": 270.0,
        "observed_at": timeutil.to_iso(AT),
        **changes,
    }


def connection() -> Connection:
    return Connection(
        id="CN-0123456789",
        name="Own ops",
        created_at=AT,
        created_by="desk:Ana K",
        key_sha256="0" * 64,
        key_hint="abcd",
    )


@pytest.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[Runtime]:
    with use_clock(FixedClock(AT)):
        built = make_runtime(make_settings(tmp_path), FixtureSource())
        yield built
        await built.aclose()


async def test_an_unset_filter_changes_nothing(runtime: Runtime) -> None:
    await tick_and_work(runtime, reason="manual")
    defaulted = runtime._expose(runtime.cones.values(), AT)
    runtime.fleet = ALL_AIRCRAFT
    explicit = runtime._expose(runtime.cones.values(), AT)

    assert FleetFilter.from_settings(Settings(_env_file=None)).everyone
    assert sorted(defaulted) == [f"{GIA417}:{SEMERU}"]
    assert defaulted == explicit
    assert runtime.exposure_aircraft() == runtime.aircraft()
    assert runtime.own_fleet() is None


def test_a_prefix_admits_its_airline_style_callsigns_only() -> None:
    fleet = FleetFilter(prefixes=frozenset({"RFA"}))
    assert fleet.admits(target())
    assert not fleet.admits(target(callsign="RFB6711"))
    assert not fleet.admits(target(callsign="RFA"))  # not airline-style: no flight number


async def test_a_listed_address_is_admitted_but_exposure_still_needs_a_flight_number(
    runtime: Runtime,
) -> None:
    await tick_and_work(runtime, reason="manual")
    runtime.fleet = FleetFilter(hexes=frozenset({"8a0f00"}))  # PKSAM, general aviation
    admitted = [a.hex for a in runtime.exposure_aircraft()]
    exposed = runtime._expose(runtime.cones.values(), AT)

    assert admitted == ["8a0f00"]
    assert exposed == {}


def test_a_pushed_position_is_always_the_airlines_own() -> None:
    fleet = FleetFilter(prefixes=frozenset({"RFA"}))
    assert fleet.admits(target(callsign="RFB6711", source_id="PUSH:CN-0123456789:091940Z"))


def test_the_settings_parse_and_refuse_bad_entries() -> None:
    settings = Settings(
        _env_file=None,
        fleet_prefixes="rfa, rfb",
        fleet_hexes="8A0A1E",
        network_airports="wiii, wadd",
    )
    assert settings.fleet_prefixes == {"RFA", "RFB"}
    assert settings.fleet_hexes == {"8a0a1e"}
    assert settings.network_airports == {"WIII", "WADD"}
    for bad in ({"fleet_prefixes": "RF"}, {"fleet_hexes": "zz0000"}, {"network_airports": "WII"}):
        with pytest.raises(ValueError, match="invalid"):
            Settings(_env_file=None, **bad)


async def test_with_a_fleet_set_only_it_and_its_pushes_are_checked(runtime: Runtime) -> None:
    runtime.fleet = FleetFilter(prefixes=frozenset({"RFA"}))
    await tick_and_work(runtime, reason="manual")
    assert runtime.exposed == {}
    assert GIA417 in {a.hex for a in runtime.aircraft()}  # still on the map

    result = await runtime.take_push(connection(), [pushed_position()])
    await tick_and_work(runtime, reason="manual")
    drafts = await list_advisories(runtime.store)

    assert result.in_ash == [PUSHED_HEX]
    assert {flight.hex for flight in runtime.exposed.values()} == {PUSHED_HEX}
    assert [d.hex for d in drafts] == [PUSHED_HEX]
    # an own TEPHRA never names a flight by an RFA number: a pushed position with no schedule
    # or registration goes by its callsign (tests/test_own_flights.py has the full order)
    assert drafts[0].proxy_flight == "RFB6711"
    assert "RFB6711" in drafts[0].body
    assert runtime.own_fleet() == OwnFleet(prefixes=["RFA"], hex_count=0)


def test_the_fleet_route_says_the_filter_and_the_state_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_tick(_: Runtime) -> None:
        return None

    def answers(settings: Settings) -> tuple[Any, Any]:
        async def factory(given: Settings) -> Runtime:
            built = make_runtime(given, FixtureSource())
            built.fleet = FleetFilter.from_settings(given)
            return built

        with TestClient(server.create_app(settings, runtime_factory=factory)) as client:
            return client.get("/api/fleet").json(), client.get("/api/state").json()

    monkeypatch.setattr(server, "_startup_tick", no_tick)
    with use_clock(FixedClock(AT)):
        unset, state = answers(make_settings(tmp_path))
        filtered, _ = answers(
            make_settings(
                tmp_path,
                fleet_prefixes="RFA,RFB",
                fleet_hexes="8a0412,8a0413",
                airline_name="Ring of Fire Air",
                airline_icao="RFB",
            )
        )

    assert unset == {"own_fleet": None}
    assert filtered == {"own_fleet": {"prefixes": ["RFA", "RFB"], "hex_count": 2}}
    assert "own_fleet" not in state
    assert "8a0412" not in str(filtered)


async def test_own_airports_are_checked_for_closure_by_code(runtime: Runtime) -> None:
    await tick_and_work(runtime, reason="manual")
    await runtime.update_own_closures(AT)
    unset = runtime.closed_now()
    recovery_before = (runtime._closed_airports, runtime.recovery_due)

    runtime.settings = runtime.settings.model_copy(
        update={"network_airports": frozenset({CLOSED, "WIII"})}
    )
    llm, runtime.llm = runtime.llm, object()  # type: ignore[assignment]  # a model call would fail
    await runtime.update_own_closures(AT)
    runtime.llm = llm
    plan = {"flight": "RFA101", "callsign": "RFA101", "origin_icao": CLOSED, "dest_icao": "WIII"}
    result = await runtime.take_push(connection(), plans=[plan])

    assert unset == frozenset()
    assert runtime.closed_now() == {CLOSED}
    assert result.closed_hits == ["RFA101"]
    assert (runtime._closed_airports, runtime.recovery_due) == recovery_before


async def test_closures_lapse_with_the_hazard(runtime: Runtime) -> None:
    runtime.settings = runtime.settings.model_copy(update={"network_airports": frozenset({CLOSED})})
    await tick_and_work(runtime, reason="manual")
    assert CLOSED in runtime.closed_now()
    runtime.cones.clear()
    runtime.situations.clear()
    await runtime.update_own_closures(AT + timedelta(minutes=1))
    assert runtime.closed_now() == frozenset()


async def test_with_a_fleet_set_other_airlines_aircraft_never_ask_for_a_model_read(
    runtime: Runtime,
) -> None:
    """The gate in front of the Plume reader counts only the aircraft the filter checks, so an
    airline's own TEPHRA spends no model quota on aircraft it never checks."""
    await tick_and_work(runtime, reason="manual")
    quiet = runtime.situations[SEMERU].model_copy(update={"discrepancies": [], "vonas": []})

    assert runtime._model_call_matters(quiet)  # the fixture's airline aircraft near the vent
    runtime.fleet = FleetFilter(prefixes=frozenset({"RFA"}))
    assert not runtime._model_call_matters(quiet)
    runtime.fleet = FleetFilter(hexes=frozenset({GIA417}))
    assert runtime._model_call_matters(quiet)
