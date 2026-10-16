"""An airline's own TEPHRA names every flight of its fleet by the airline's own name for it: its
own callsign, else its flight in the airline's schedule, else its registration; never a
fictional RFA number. The shared demo (no own fleet) is unchanged: RFA numbers and the
fictional airline's labels."""

import json
import re
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_fleet_filter import PUSHED_HEX, connection, pushed_position, target
from test_pipeline import AT, FixtureSource, make_runtime, make_settings, tick_and_work

from tephra.agents.dispatch_drafter import HEADER_TITLE
from tephra.config import DEMO_AIRLINE, Settings
from tephra.desk import audit
from tephra.desk.approvals import list_advisories
from tephra.desk.crew_reports import CrewEntry
from tephra.geo.fleet import FleetFilter, OwnSchedule, ScheduleError
from tephra.models import CrewCue, PushedFlightPlan, SseEvent
from tephra.pipeline import Runtime
from tephra.regdocs.crew_message import draft_crew_message
from tephra.regdocs.var import draft_var
from tephra.util.hashing import proxy_flight_number
from tephra.util.timeutil import FixedClock, use_clock

RFA_NUMBER = re.compile(r"\bRFA\d{4}\b")
"""A fictional proxy number (RFA + 4 digits); an own TEPHRA must never write one."""
OWN = {
    "fleet_prefixes": "RFB",
    "airline_name": "Ring of Fire Air",
    "airline_icao": "RFB",
    "airline_iata": "RB",
}
REGISTRATION = "PK-RFB"
OWN_HEADER = "TEPHRA COMPANY ADVISORY - RING OF FIRE AIR - NOT FOR OPERATIONAL USE"
WET_LEASE = "RFA401"
"""An airline-style callsign that is not the airline's own (three digits, so never mistaken
for a four-digit RFA proxy number): a pushed aircraft flying it is named by the schedule or
its registration."""


def schedule(tmp_path: Path, *, std_min: int, days: str | None = None) -> OwnSchedule:
    """flights.json and fleet.json as the setup kit writes them. AT is 02:40 local (UTC+7) on
    Saturday 10 Oct 2026."""
    folder = tmp_path / "airline"
    folder.mkdir(exist_ok=True)
    row: dict[str, Any] = {
        "flight_no": "RB401",
        "origin": "WARR",
        "dest": "WADD",
        "std_min": std_min,
        "block_min": 90,
        "tail": REGISTRATION,
        **({"days": days} if days else {}),
    }
    flights = {"header": {"label": "RFB schedule", "anchor_utc_offset_h": 7}, "flights": [row]}
    fleet = {"tails": [{"tail": REGISTRATION, "type": "A320", "seats": 180, "hex": PUSHED_HEX}]}
    (folder / "flights.json").write_text(json.dumps(flights), encoding="utf-8")
    (folder / "fleet.json").write_text(json.dumps(fleet), encoding="utf-8")
    return OwnSchedule.load(tmp_path, "airline/flights.json", "airline/fleet.json")


@pytest.fixture
async def own(tmp_path: Path) -> AsyncIterator[Runtime]:
    with use_clock(FixedClock(AT)):
        settings = make_settings(tmp_path, **OWN)
        built = make_runtime(settings, FixtureSource())
        built.fleet = FleetFilter.from_settings(settings)
        yield built
        await built.aclose()


async def own_run(runtime: Runtime, **position: Any) -> list[Any]:
    await tick_and_work(runtime, reason="manual")
    await runtime.take_push(connection(), [pushed_position(**position)])
    await tick_and_work(runtime, reason="manual")
    return await list_advisories(runtime.store)


def written(runtime: Runtime, drafts: list[Any], entries: list[Any]) -> str:
    """Everything the run wrote that names a flight: drafts, audit, exposure and the trace."""
    trace = [event.data for event in runtime.bus.recent(SseEvent.TRACE, limit=200)]
    return json.dumps(
        [
            [d.model_dump(mode="json") for d in drafts],
            [e.model_dump(mode="json") for e in entries],
            [f.model_dump(mode="json") for f in runtime.exposed.values()],
            trace,
        ]
    )


# --- the order of names ------------------------------------------------------------------


def test_the_airlines_own_callsign_names_its_flight(tmp_path: Path) -> None:
    fleet = FleetFilter(
        prefixes=frozenset({"RFB"}), icao="RFB", schedule=schedule(tmp_path, std_min=120)
    )
    for callsign in ("RFB401", "RFB6711"):
        assert fleet.flight_name(PUSHED_HEX, callsign, AT, own=True) == callsign


def test_the_icao_designator_counts_as_the_airlines_callsign() -> None:
    fleet = FleetFilter(hexes=frozenset({PUSHED_HEX}), icao="RFB")
    assert fleet.flight_name(PUSHED_HEX, "RFB401", AT, own=True) == "RFB401"


def test_else_a_pushed_plan_flying_now_names_it() -> None:
    fleet = FleetFilter(prefixes=frozenset({"RFB"}))
    flying = PushedFlightPlan(
        flight="RB977",
        hex=PUSHED_HEX,
        origin_icao="WARR",
        dest_icao="WADD",
        std=AT - timedelta(minutes=30),
        sta=AT + timedelta(minutes=60),
    )
    later = flying.model_copy(
        update={"std": AT + timedelta(hours=3), "sta": AT + timedelta(hours=4)}
    )
    assert fleet.flight_name(PUSHED_HEX, WET_LEASE, AT, own=True, plans=[flying]) == "RB977"
    assert fleet.flight_name(PUSHED_HEX, WET_LEASE, AT, own=True, plans=[later]) == WET_LEASE


def test_else_the_schedule_names_it_by_registration_and_time(tmp_path: Path) -> None:
    fleet = FleetFilter(prefixes=frozenset({"RFB"}), schedule=schedule(tmp_path, std_min=120))
    assert fleet.flight_name(PUSHED_HEX, WET_LEASE, AT, own=True) == "RB401"
    assert fleet.flight_name(PUSHED_HEX, None, AT, own=True) == "RB401"


def test_a_flight_departing_after_midnight_local_belongs_to_the_day_before(
    tmp_path: Path,
) -> None:
    """std_min 1560 is 02:00 local on the next day: Friday's 1560 departs Saturday 02:00."""
    friday = FleetFilter(
        prefixes=frozenset({"RFB"}), schedule=schedule(tmp_path, std_min=1560, days="5")
    )
    saturday = FleetFilter(
        prefixes=frozenset({"RFB"}), schedule=schedule(tmp_path, std_min=120, days="1234")
    )
    assert friday.flight_name(PUSHED_HEX, None, AT, own=True) == "RB401"
    assert saturday.flight_name(PUSHED_HEX, None, AT, own=True) == REGISTRATION


def test_else_the_registration_names_it(tmp_path: Path) -> None:
    """Not departed yet (std 10:00 local), or later than its arrival by more than the block
    time (Friday 23:00 local): the schedule cannot say which flight it is, and the
    registration is never wrong."""
    for std_min in (600, 1380):
        fleet = FleetFilter(
            prefixes=frozenset({"RFB"}), schedule=schedule(tmp_path, std_min=std_min)
        )
        assert fleet.flight_name(PUSHED_HEX, WET_LEASE, AT, own=True) == REGISTRATION


def test_two_flights_at_one_minute_name_neither(tmp_path: Path) -> None:
    own = schedule(tmp_path, std_min=120)
    twin = own.rows[0].model_copy(update={"flight_no": "RB402"})
    fleet = FleetFilter(
        prefixes=frozenset({"RFB"}), schedule=OwnSchedule(7, (*own.rows, twin), own.registrations)
    )
    assert fleet.flight_name(PUSHED_HEX, None, AT, own=True) == REGISTRATION


def test_with_nothing_known_it_goes_by_what_ads_b_says_and_another_airline_too() -> None:
    fleet = FleetFilter(prefixes=frozenset({"RFB"}))
    assert fleet.flight_name(PUSHED_HEX, WET_LEASE, AT, own=True) == WET_LEASE
    assert fleet.flight_name(PUSHED_HEX, None, AT, own=True) == PUSHED_HEX.upper()
    assert fleet.flight_name("8a0123", "RFA417", AT, own=False) == "RFA417"
    named = fleet.named(target(callsign="RFA417"), AT)
    assert named.proxy_flight == "RFA417"
    assert named.model_dump()["proxy_flight"] == "RFA417"


def test_the_demo_names_every_aircraft_by_its_rfa_number() -> None:
    aircraft = target()
    demo = FleetFilter()
    assert demo.named(aircraft, AT) is aircraft
    assert aircraft.proxy_flight == proxy_flight_number(aircraft.hex)
    assert not aircraft.own_named
    assert "_own_flight" not in aircraft.model_dump_json()


def test_unreadable_files_stop_startup(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path, data_dir=tmp_path, airline_schedule="airline/flights.json", **OWN
    )
    with pytest.raises(ScheduleError, match=r"flights\.json"):
        FleetFilter.from_settings(settings)
    folder = tmp_path / "airline"
    folder.mkdir()
    (folder / "flights.json").write_text(
        json.dumps(
            {
                "header": {"anchor_utc_offset_h": None},
                "flights": [{"flight_no": "RB401", "std_min": 1, "block_min": 1}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ScheduleError, match="anchor_utc_offset_h"):
        FleetFilter.from_settings(settings)
    (folder / "flights.json").write_text(
        json.dumps({"header": {"label": "fill in", "anchor_utc_offset_h": None}, "flights": []}),
        encoding="utf-8",
    )
    assert FleetFilter.from_settings(settings).schedule.rows == ()  # the kit's unfilled file


# --- the settings --------------------------------------------------------------------------


def test_the_airline_settings_need_an_own_fleet_and_an_own_fleet_needs_them() -> None:
    assert Settings(_env_file=None).airline == DEMO_AIRLINE
    with pytest.raises(ValueError, match="only for an airline's own TEPHRA"):
        Settings(_env_file=None, airline_name="Ring of Fire Air")
    with pytest.raises(ValueError, match="needs TEPHRA_AIRLINE_NAME"):
        _ = Settings(_env_file=None, fleet_prefixes="RFB").airline
    airline = Settings(_env_file=None, **{**OWN, "airline_icao": "rfb"}).airline
    assert (airline.code, airline.name, airline.iata, airline.fictional) == (
        "RFB",
        "Ring of Fire Air",
        "RB",
        False,
    )
    assert airline.label == "Ring of Fire Air"
    assert airline.operator == "Ring of Fire Air (ICAO RFB, IATA RB)"
    assert airline.disclaimer == "Decision support only - not for operational use"


# --- end to end ------------------------------------------------------------------------------


async def test_an_own_run_names_the_flight_by_its_own_callsign(own: Runtime) -> None:
    drafts = await own_run(own, callsign="RFB6711")
    entries = await audit.list_entries(own.store)
    wall = await own.wall_snapshot()
    labels = [f["properties"]["label"] for f in wall.aircraft["features"] if f["id"] == PUSHED_HEX]
    state = (await own.system_state()).model_dump(mode="json")

    assert [d.proxy_flight for d in drafts] == ["RFB6711"]
    header = drafts[0].header.splitlines()
    assert header[0] == OWN_HEADER
    assert header[1].startswith("RFB6711 (ADS-B RFB6711 ")
    assert "RFB6711" in drafts[0].body
    assert labels
    assert labels[0].startswith("RFB6711 ")
    assert state["airline"] == {"code": "RFB", "name": "Ring of Fire Air", "fictional": False}
    assert state["disclaimer"] == "Decision support only - not for operational use"
    text = written(own, drafts, entries)
    assert "RFB6711" in text
    assert not RFA_NUMBER.search(text)
    assert "FICTIONAL" not in text.upper()


async def test_an_own_runs_documents_and_crew_notice_name_the_airline(own: Runtime) -> None:
    await own_run(own, callsign="RFB6711")
    var = await draft_var(own, next(iter(own.exposed)))
    entry = CrewEntry(
        hex=PUSHED_HEX,
        cues=[CrewCue.ASH_SEEN],
        level_from_fl=100,
        level_to_fl=140,
        observed_at=AT,
    )
    view = await own.enter_crew_report(entry, actor="desk:Test")
    notice = await draft_crew_message(own, view, vaac=None)
    fields = {f.key: f.value for f in [*var.header_fields, *notice.to]}
    text = json.dumps([var.model_dump(mode="json"), notice.model_dump(mode="json")])

    assert fields["operator"] == "Ring of Fire Air (ICAO RFB, IATA RB)"
    assert fields["ac_ident"] == "RFB6711"
    assert fields["from"] == "Ring of Fire Air dispatch"
    assert view.report.proxy_flight == "RFB6711"
    assert "Decision support only - not for operational use" in var.labels
    assert "Decision support only - not for operational use" in notice.labels
    assert "RFB6711 (Ring of Fire Air flight" in notice.body
    assert "FICTIONAL" not in text.upper()
    assert not RFA_NUMBER.search(text)


async def test_an_own_run_names_a_wet_leased_callsign_by_the_schedule(
    own: Runtime, tmp_path: Path
) -> None:
    own.fleet = FleetFilter(
        prefixes=frozenset({"RFB"}), icao="RFB", schedule=schedule(tmp_path, std_min=120)
    )
    drafts = await own_run(own, callsign=WET_LEASE)
    entries = await audit.list_entries(own.store)

    assert [d.proxy_flight for d in drafts] == ["RB401"]
    assert drafts[0].header.splitlines()[1].startswith(f"RB401 (ADS-B {WET_LEASE} ")
    assert own.crew_fix(PUSHED_HEX, None, AT).proxy_flight == "RB401"
    assert not RFA_NUMBER.search(written(own, drafts, entries))


async def test_an_own_run_names_it_by_registration_off_schedule(
    own: Runtime, tmp_path: Path
) -> None:
    own.fleet = FleetFilter(
        prefixes=frozenset({"RFB"}), icao="RFB", schedule=schedule(tmp_path, std_min=600)
    )
    drafts = await own_run(own, callsign=WET_LEASE)

    assert [d.proxy_flight for d in drafts] == [REGISTRATION]
    assert REGISTRATION in drafts[0].body
    assert not RFA_NUMBER.search(written(own, drafts, []))


async def test_the_demo_run_is_unchanged(tmp_path: Path) -> None:
    """The shared demo: RFA numbers, the fictional airline's header and state."""
    with use_clock(FixedClock(AT)):
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            drafts = await own_run(runtime)
            state = (await runtime.system_state()).model_dump(mode="json")
        finally:
            await runtime.aclose()

    assert drafts
    for draft in drafts:
        assert draft.proxy_flight == proxy_flight_number(draft.hex)
        assert draft.header.splitlines()[0] == HEADER_TITLE
    assert HEADER_TITLE == (
        "TEPHRA COMPANY ADVISORY - RING OF FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL USE"
    )
    assert state["airline"] == {"code": "RFA", "name": "Ring of Fire Air", "fictional": True}
    assert (
        state["disclaimer"] == "Decision support only - fictional airline - not for operational use"
    )
