"""Network recovery: the RFA schedule, closures, the CP-SAT solver, the ADK agent run offline
against a scripted model, the plan state machine and the HTTP routes.

The demo instance is the 5-7 Sep 2026 Anak Krakatau closure of CGK and HLP (NOTAM: from 01:28Z
to 11:00Z on 7 Sep). No network, no real model.
"""

import asyncio
import importlib.util
import json
import time
from collections import defaultdict
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.models.registry import LLMRegistry
from google.genai import types

from tephra.agents.llm import LlmBackendName
from tephra.api.auth import require_desk
from tephra.api.routes_recovery import router
from tephra.api.server import _install_error_handlers
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk import audit
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.models import (
    Airport,
    AuditAction,
    FeedId,
    GeoPolygon,
    HazardCone,
    Metar,
    OfficialLayer,
    OperatorPolicy,
    PlumeMode,
    Provenance,
    RunMode,
    SessionInfo,
    SseEvent,
    Taf,
    TafPeriod,
    TraceEvent,
    polygon_from_latlon,
)
from tephra.policy import load_policy
from tephra.recovery import decisions
from tephra.recovery.agent import PROMPT_PATH, build_recovery_agent, recommend_recovery
from tephra.recovery.closures import find_closures, merge_closures
from tephra.recovery.models import (
    Closure,
    RecoveryActionKind,
    RecoveryPlan,
    RecoveryScenario,
    RfaCrew,
    RfaFlight,
    RfaTail,
    RfaTemplateFlight,
    Schedule,
    ScheduleHeader,
    SolveStatus,
)
from tephra.recovery.schedule import ScheduleError, load_schedule
from tephra.recovery.solver import describe_disruption, solve_recovery
from tephra.recovery.tools import Recommendation, Toolbox, validate_recommendation
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock

DATA = PROJECT_ROOT / "data"
POLICY = load_policy(DATA)
RULES = POLICY.recovery
CATALOGUE = load_airports(DATA, min_runway_m=POLICY.alternates.min_runway_m.value)
AIRPORTS = {airport.icao: airport for airport in CATALOGUE.all()}
NOW = datetime(2026, 9, 7, 1, 0, tzinfo=UTC)
CGK, HLP = "WIII", "WIHH"
SCRIPTED_MODEL = "tephra-recovery-scripted"


def notam_closures() -> list[Closure]:
    start = datetime(2026, 9, 7, 1, 28, tzinfo=UTC)
    end = datetime(2026, 9, 7, 11, 0, tzinfo=UTC)
    return [
        Closure(icao=icao, start=start, end=end, reason="NOTAM CLOSURE", source_ids=["NOTAM"])
        for icao in (CGK, HLP)
    ]


@pytest.fixture(scope="module")
def schedule() -> Schedule:
    return load_schedule(DATA, NOW)


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    with use_clock(FixedClock(NOW)):
        yield


@pytest.fixture(scope="module")
def demo(schedule: Schedule) -> dict[int, RecoveryScenario]:
    """The three scenarios of the demo instance, each timed end to end."""
    scenarios = {}
    for extend in (0, RULES.scenario_extend_1_min.value, RULES.scenario_extend_2_min.value):
        started = time.perf_counter()
        scenarios[extend] = solve_recovery(
            schedule,
            notam_closures(),
            now=NOW,
            policy=POLICY,
            airports=AIRPORTS,
            extend_min=extend,
        )
        took_s = time.perf_counter() - started
        assert took_s < RULES.solve_time_limit_s.value, f"+{extend} min took too long"
    return scenarios


# --- the schedule -------------------------------------------------------------------------------


def test_the_schedule_is_a_labelled_synthetic_day(schedule: Schedule) -> None:
    assert len(schedule.tails) == 30
    assert len(schedule.flights) == 2 * 142
    assert {f.day_offset for f in schedule.flights} == {0, 1}
    assert "fictional" in schedule.header.label
    assert {t.home_base for t in schedule.tails} == {"WIII", "WARR", "WADD", "WAAA", "WIMM"}
    assert all(f.origin in AIRPORTS and f.dest in AIRPORTS for f in schedule.flights)
    assert schedule.day.isoformat() == "2026-09-07"
    assert schedule.at(0) == datetime(2026, 9, 6, 17, 0, tzinfo=UTC)


def test_the_schedule_follows_the_clock_s_local_day(schedule: Schedule) -> None:
    late = load_schedule(DATA, datetime(2026, 9, 7, 18, 0, tzinfo=UTC))  # 01:00 WIB on 8 Sep
    assert late.day.isoformat() == "2026-09-08"
    assert [f.flight_no for f in late.flights] == [f.flight_no for f in schedule.flights]
    assert late.flights[0].key == "RFA101/08SEP"
    assert late.flights[-1].service_date.isoformat() == "2026-09-09"


def test_the_window_holds_two_days_under_unique_keys(schedule: Schedule) -> None:
    keys = [f.key for f in schedule.flights]
    assert len(set(keys)) == len(keys) == 284
    today = {f.flight_no: f for f in schedule.flights if f.day_offset == 0}
    tomorrow = {f.flight_no: f for f in schedule.flights if f.day_offset == 1}
    assert today.keys() == tomorrow.keys()
    assert "RFA101/07SEP" in keys
    assert "RFA101/08SEP" in keys
    for number, first in today.items():
        second = tomorrow[number]
        assert second.std_min == first.std_min + 1440
        assert schedule.at(second.std_min) - schedule.at(first.std_min) == timedelta(days=1)
        assert (second.origin, second.dest, second.tail) == (first.origin, first.dest, first.tail)


def test_the_build_script_reproduces_the_committed_files(schedule: Schedule) -> None:
    spec = importlib.util.spec_from_file_location(
        "build_rfa_schedule", PROJECT_ROOT / "scripts" / "build_rfa_schedule.py"
    )
    assert spec is not None
    assert spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    tails, crews, flights = script.build({a.icao: a for a in CATALOGUE.all()})
    assert tails == schedule.tails
    assert crews == schedule.crews
    today = [f for f in schedule.flights if f.day_offset == 0]
    template = [
        RfaTemplateFlight(**f.model_dump(exclude={"service_date", "day_offset", "key"}))
        for f in today
    ]
    assert sorted(flights, key=lambda f: (f.std_min, f.flight_no)) == template


def test_every_excursion_is_a_real_route(schedule: Schedule) -> None:
    path = DATA / "routes_apac.json"
    if not path.is_file():
        pytest.skip("data/routes_apac.json is not built")
    chains = json.loads(path.read_text(encoding="utf-8"))["routes"].values()
    real = {frozenset(hop) for chain in chains for hop in pairwise(chain.split("-"))}
    assert {frozenset((f.origin, f.dest)) for f in schedule.flights} <= real


def test_an_inconsistent_schedule_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "rfa"
    folder.mkdir()
    for name in ("fleet.json", "crews.json", "flights.json"):
        (folder / name).write_text((DATA / "rfa" / name).read_text())
    text = (folder / "flights.json").read_text().replace('"dest": "WIDD"', '"dest": "WIII"', 1)
    (folder / "flights.json").write_text(text)
    with pytest.raises(ScheduleError):
        load_schedule(tmp_path, NOW)
    with pytest.raises(ScheduleError):
        load_schedule(tmp_path / "missing", NOW)


# --- closures -----------------------------------------------------------------------------------


def make_cone(lat: float, lon: float, *, base_ft: int = 0, hours: int = 6) -> HazardCone:
    half = 0.2
    ring = [(lat - half, lon - half), (lat - half, lon + half), (lat + half, lon + half)]
    ring.append((lat + half, lon - half))
    return HazardCone(
        id="CONE-0123456789ab",
        volcano_id="262000",
        assessment_id="PA-0123456789ab",
        mode=PlumeMode.OFFICIAL,
        confidence=0.9,
        llm_backend="stub",
        created_at=NOW,
        horizon_h=float(hours),
        valid_to=NOW + timedelta(hours=hours),
        geometry=polygon_from_latlon(ring),
        base_ft=base_ft,
        top_ft=40_000,
        official_source_ids=["SIGMET:WIIF:1"],
    )


def taf_with(weather: list[str], icao: str = "WARR") -> Taf:
    period = TafPeriod(
        valid_from=NOW + timedelta(hours=2), valid_to=NOW + timedelta(hours=5), weather=weather
    )
    return Taf(
        provenance=provenance(f"TAF:{icao}:1"),
        icao=icao,
        issued_at=NOW,
        valid_from=NOW,
        valid_to=NOW + timedelta(hours=24),
        periods=[period],
        raw_text="TAF",
    )


def provenance(source_id: str) -> Provenance:
    return Provenance(
        source_id=source_id,
        feed=FeedId.TAF,
        url="https://example.test",
        fetched_at=NOW,
        sha256="0" * 64,
    )


def closures_for(
    airports: list[Airport], cones: list[HazardCone] = (), **kwargs: Any
) -> list[Closure]:
    return find_closures(
        airports,
        cones=list(cones),
        layers=kwargs.get("layers", []),
        tafs=kwargs.get("tafs", {}),
        metars=kwargs.get("metars", {}),
        at=NOW,
        horizon_end=NOW + timedelta(hours=18),
        policy=POLICY,
    )


def test_an_airport_near_the_cone_is_closed_for_the_cone_s_validity() -> None:
    jakarta = AIRPORTS[CGK]
    found = closures_for([jakarta, AIRPORTS["WARR"]], [make_cone(jakarta.lat, jakarta.lon)])
    assert [c.icao for c in found] == [CGK]
    assert found[0].start == NOW
    assert found[0].end == NOW + timedelta(hours=6)
    assert "CONE-0123456789ab" in found[0].reason
    assert "SIGMET:WIIF:1" in found[0].source_ids


def test_the_closure_radius_is_the_policy_s() -> None:
    jakarta = AIRPORTS[CGK]
    radius = RULES.airport_closure_radius_nm.value
    offset_deg = (radius + 6) / 60.0  # the cone edge is 0.2 degrees (12 NM) from its centre
    assert not closures_for([jakarta], [make_cone(jakarta.lat + offset_deg + 0.2, jakarta.lon)])
    assert closures_for([jakarta], [make_cone(jakarta.lat + offset_deg - 0.2, jakarta.lon)])


def test_a_cone_that_stays_above_fl100_does_not_close_an_airport() -> None:
    jakarta = AIRPORTS[CGK]
    assert not closures_for([jakarta], [make_cone(jakarta.lat, jakarta.lon, base_ft=12_000)])


def test_an_official_layer_closes_an_airport_in_its_own_window() -> None:
    airport = AIRPORTS["WADD"]
    ring = [(airport.lat - 0.1, airport.lon - 0.1), (airport.lat - 0.1, airport.lon + 0.1)]
    ring += [(airport.lat + 0.1, airport.lon + 0.1)]
    layer = OfficialLayer(
        source_id="SIGMET:WADD:9",
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WAAF 9",
        polygon=cast(GeoPolygon, polygon_from_latlon(ring)),
        base_ft=0,
        top_ft=30_000,
        valid_from=NOW + timedelta(hours=1),
        valid_to=NOW + timedelta(hours=4),
    )
    (closure,) = closures_for([airport], layers=[layer])
    assert (closure.start, closure.end) == (layer.valid_from, layer.valid_to)
    assert closure.source_ids == ["SIGMET:WADD:9"]


def test_a_taf_with_va_closes_only_that_period_and_a_metar_with_va_is_open_ended() -> None:
    airport = AIRPORTS["WARR"]
    (by_taf,) = closures_for([airport], tafs={"WARR": taf_with(["VA"])})
    assert by_taf.start == NOW + timedelta(hours=2)
    assert not by_taf.open_ended
    assert not closures_for([airport], tafs={"WARR": taf_with(["TSRA"])})
    metar = Metar(
        provenance=provenance("METAR:WARR:1"),
        icao="WARR",
        observed_at=NOW,
        weather=["VA"],
        raw_text="METAR",
    )
    (by_metar,) = closures_for([airport], metars={"WARR": metar})
    assert by_metar.open_ended
    assert by_metar.end == NOW + timedelta(hours=18)


def test_overlapping_closures_of_one_airport_merge() -> None:
    first = Closure(icao=CGK, start=NOW, end=NOW + timedelta(hours=3), reason="A", source_ids=["a"])
    second = first.model_copy(
        update={"start": NOW + timedelta(hours=2), "end": NOW + timedelta(hours=5), "reason": "B"}
    )
    later = first.model_copy(
        update={"start": NOW + timedelta(hours=9), "end": NOW + timedelta(hours=10)}
    )
    merged = merge_closures([second, first, later])
    assert [(c.start, c.end) for c in merged] == [
        (NOW, NOW + timedelta(hours=5)),
        (NOW + timedelta(hours=9), NOW + timedelta(hours=10)),
    ]
    assert merged[0].reason == "A; B"


def test_a_closure_has_a_short_code_written_summary_beside_its_full_reason() -> None:
    jakarta = AIRPORTS[CGK]
    ring = [(jakarta.lat - 0.1, jakarta.lon - 0.1), (jakarta.lat - 0.1, jakarta.lon + 0.1)]
    ring += [(jakarta.lat + 0.1, jakarta.lon + 0.1)]
    layers = [
        OfficialLayer(
            source_id=f"{kind}:WIII:{n}",
            kind=kind,  # type: ignore[arg-type]
            layer="SIGMET" if kind == "SIGMET" else "OBS",
            label=f"{kind} WIII {n}",
            polygon=cast(GeoPolygon, polygon_from_latlon(ring)),
            base_ft=0,
            top_ft=top,
            valid_from=NOW + timedelta(hours=1),
            valid_to=NOW + timedelta(hours=4),
        )
        for n, (kind, top) in enumerate((("SIGMET", 20_000), ("VAA", 30_000), ("SIGMET", 10_000)))
    ]
    (closure,) = closures_for([jakarta], layers=layers)
    assert closure.summary == "Ash SFC/FL300 within 20 NM · 3 official products"
    assert closure.reason.count("NEAR WIII") == 3  # the full reason is kept for audit
    assert len(closure.source_ids) == 3
    assert closure.model_dump(mode="json")["summary"] == closure.summary  # served by the API

    cone = make_cone(jakarta.lat, jakarta.lon)
    (by_cone,) = closures_for([jakarta], [cone])
    assert by_cone.summary == "Ash SFC/FL400 within 20 NM · 1 official product"
    entered = Closure(
        icao=CGK, start=NOW, end=NOW + timedelta(hours=1), reason="X", basis=["ENTERED"]
    )
    assert entered.summary == "Entered by dispatcher"
    metar = merge_closures([entered, entered.model_copy(update={"basis": ["METAR"]})])[0]
    assert metar.summary == "METAR reports VA · Entered by dispatcher"
    assert metar.basis == ["ENTERED", "METAR"]


# --- the solver ---------------------------------------------------------------------------------


@dataclass
class Leg:
    flight_no: str
    tail: str
    origin: str
    dest: str
    std: int
    block: int


def check_plan(schedule: Schedule, scenario: RecoveryScenario, now: datetime = NOW) -> None:
    """Re-check a plan against the rules without the solver: closures, turns, positions,
    ferry legs, seats, duty, the delay limit, pairs and what must not move."""
    assert scenario.totals is not None
    now_min = schedule.minutes_of(now)
    windows: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for closure in scenario.closures:
        windows[closure.icao].append(
            (schedule.minutes_of(closure.start), schedule.minutes_of(closure.end))
        )

    def closed(icao: str, minute: float) -> bool:
        return any(start <= minute < end for start, end in windows[icao])

    actions = {a.flight_key: a for a in scenario.actions}
    seats = {t.tail: t.seats for t in schedule.tails}
    reports = {c.crew_id: c.report_min for c in schedule.crews}
    limit = {t.tail: reports[t.crew_id] + RULES.max_fdp_min.value for t in schedule.tails}
    chains: dict[str, list[Leg]] = defaultdict(list)
    for flight in schedule.flights:
        action = actions.get(flight.key)
        if action is not None:
            assert flight.std_min >= now_min, "a flight that had left was changed"
            assert action.tail == flight.tail
        if action is not None and action.kind is RecoveryActionKind.CANCEL:
            continue
        delay = action.delay_min if action else 0
        tail = action.new_tail if action and action.new_tail else flight.tail
        std = flight.std_min + delay
        assert delay <= scenario.max_delay_min
        assert delay % 5 == 0
        assert flight.pax_booked <= seats[tail]
        if flight.std_min >= now_min:
            assert not closed(flight.origin, std)
            assert not closed(flight.dest, std + flight.block_min)
            assert std + flight.block_min <= limit[tail] + 1440 * flight.day_offset
        chains[tail].append(
            Leg(flight.key, tail, flight.origin, flight.dest, std, flight.block_min)
        )
    ferries: dict[str, list[Any]] = defaultdict(list)
    for leg in scenario.ferry_legs:
        assert not closed(leg.origin, schedule.minutes_of(leg.dep))
        assert not closed(leg.dest, schedule.minutes_of(leg.arr))
        ferries[leg.tail].append(leg)
    turn = RULES.min_turn_min.value
    first_origin = {
        t.tail: next(f.origin for f in schedule.flights if f.tail == t.tail) for t in schedule.tails
    }
    for tail, chain in chains.items():
        chain.sort(key=lambda leg: leg.std)
        position, ready = first_origin[tail], -1.0
        for leg in chain:
            if leg.origin != position:
                hop = next(
                    f for f in ferries[tail] if f.origin == position and f.dest == leg.origin
                )
                assert schedule.minutes_of(hop.dep) >= ready
                ready = schedule.minutes_of(hop.arr) + turn
            assert leg.std >= ready, f"{tail}: {leg.flight_no} leaves before the aircraft is ready"
            position, ready = leg.dest, leg.std + leg.block + turn
    by_pair: dict[tuple[str | None, Any], set[bool]] = defaultdict(set)
    for flight in schedule.flights:
        if flight.pair_id is not None and flight.key in actions:
            by_pair[(flight.pair_id, flight.service_date)].add(
                actions[flight.key].kind is RecoveryActionKind.CANCEL
            )
    cancelled_pairs = {
        pair
        for pair in by_pair
        if all(
            flight.key in actions and actions[flight.key].kind is RecoveryActionKind.CANCEL
            for flight in schedule.flights
            if (flight.pair_id, flight.service_date) == pair
        )
    }
    for pair in by_pair:
        members = [
            f
            for f in schedule.flights
            if (f.pair_id, f.service_date) == pair and f.std_min >= now_min
        ]
        statuses = {
            f.key in actions and actions[f.key].kind is RecoveryActionKind.CANCEL for f in members
        }
        assert len(statuses) == 1 or not cancelled_pairs, f"{pair} is cancelled in part"


def test_the_demo_instance_solves_each_scenario_in_under_two_seconds(
    demo: dict[int, RecoveryScenario],
) -> None:
    for scenario in demo.values():
        assert scenario.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)
        assert scenario.solve_ms < RULES.solve_time_limit_s.value * 1000


def test_every_demo_plan_obeys_the_rules(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    for scenario in demo.values():
        check_plan(schedule, scenario)


def test_a_longer_closure_never_costs_less(demo: dict[int, RecoveryScenario]) -> None:
    costs = [demo[e].totals.total_usd for e in sorted(demo)]  # type: ignore[union-attr]
    assert costs == sorted(costs)
    assert demo[0].label == "CLOSURE AS FORECAST"
    assert demo[RULES.scenario_extend_1_min.value].label == "CLOSURE +180 MIN"


def test_totals_add_up_from_the_actions(demo: dict[int, RecoveryScenario]) -> None:
    for scenario in demo.values():
        totals = scenario.totals
        assert totals is not None
        cancelled = [a for a in scenario.actions if a.kind is RecoveryActionKind.CANCEL]
        assert totals.cancelled_flights == len(cancelled)
        assert totals.pax_cancelled == sum(a.pax_booked for a in cancelled)
        assert totals.cancel_usd == sum(
            a.pax_booked * RULES.cancel_cost_per_pax_usd.value + RULES.cancel_cost_fixed_usd.value
            for a in cancelled
        )
        assert totals.swap_usd == totals.swapped_flights * RULES.swap_cost_usd.value
        assert totals.total_usd == (
            totals.delay_usd + totals.cancel_usd + totals.swap_usd + totals.ferry_usd
        )
        assert (
            totals.kept_flights + len({a.flight_key for a in scenario.actions})
            == totals.free_flights
        )


def test_flights_blocked_by_the_closure_are_not_flown_into_it(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    found = describe_disruption(schedule, notam_closures(), now=NOW, policy=POLICY)
    assert found.blocked_flights
    assert found.airborne_at_risk
    assert found.frozen_flights + found.free_flights <= len(schedule.flights)
    plan = demo[0]
    changed = {a.flight_key for a in plan.actions}
    assert set(found.blocked_flights) <= changed


def test_a_flight_that_has_left_or_is_about_to_is_never_moved(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    edge = schedule.minutes_of(NOW) + RULES.freeze_window_min.value
    moved = {a.flight_key for s in demo.values() for a in s.actions}
    free_start = {f.key for f in schedule.flights if f.std_min >= schedule.minutes_of(NOW)}
    assert moved <= free_start
    stable = {
        f.key
        for f in schedule.flights
        if f.std_min < edge and not (f.origin in (CGK, HLP) or f.dest in (CGK, HLP))
    }
    assert not stable & moved


def test_the_same_disruption_gives_the_same_plan_every_run(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    """A deterministic search limit: the dispatcher, the replay and the video see one plan."""
    again = solve_recovery(schedule, notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS)
    first = demo[0]
    assert again.totals == first.totals
    assert [(a.flight_key, a.kind, a.delay_min) for a in again.actions] == [
        (a.flight_key, a.kind, a.delay_min) for a in first.actions
    ]


def test_protecting_a_flight_keeps_it_flying(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    # The latest cancelled CGK departure that can still wait for the reopening: a later one
    # fails on its crew's duty limit, and the solver says so (next test).
    candidates = sorted(
        (a for a in demo[0].actions if a.kind is RecoveryActionKind.CANCEL and a.origin == CGK),
        key=lambda a: a.std,
        reverse=True,
    )
    for cancelled in candidates:
        scenario = solve_recovery(
            schedule,
            notam_closures(),
            now=NOW,
            policy=POLICY,
            airports=AIRPORTS,
            protect_flights=[cancelled.flight_key],
        )
        if scenario.status is not SolveStatus.NO_PLAN:
            break
    else:
        pytest.fail("no cancelled CGK departure can be protected")
    kept = {a.flight_key: a for a in scenario.actions}.get(cancelled.flight_key)
    assert kept is None or kept.kind is not RecoveryActionKind.CANCEL
    check_plan(schedule, scenario)
    assert scenario.totals is not None
    assert demo[0].totals is not None
    assert scenario.totals.total_usd >= demo[0].totals.total_usd


def test_protecting_a_flight_the_crew_cannot_legally_fly_makes_no_plan(
    schedule: Schedule,
) -> None:
    """RFA231 leaves CGK at 16:00 local, before the reopening. Its excursion partner RFA192 would
    have to wait for the reopening too, and the pair would end after the crew's duty limit; the
    solver says so and nothing is substituted."""
    scenario = solve_recovery(
        schedule,
        notam_closures(),
        now=NOW,
        policy=POLICY,
        airports=AIRPORTS,
        protect_flights=["RFA231/07SEP"],
    )
    assert scenario.status is SolveStatus.NO_PLAN
    assert scenario.solver_status == "INFEASIBLE"


KRAKATAU_NOW = datetime(2026, 9, 5, 10, 30, tzinfo=UTC)  # 17:30 WIB, the day is nearly over


def krakatau_closures() -> list[Closure]:
    """CGK closed from 05 SEP 10:10Z to 06 SEP 07:10Z, as in the Anak Krakatau replay."""
    return [
        Closure(
            icao=CGK,
            start=datetime(2026, 9, 5, 10, 10, tzinfo=UTC),
            end=datetime(2026, 9, 6, 7, 10, tzinfo=UTC),
            reason="TEST CLOSURE",
            source_ids=["TEST"],
        )
    ]


def test_a_late_evening_closure_still_has_a_whole_day_to_re_plan() -> None:
    """With one day anchored to the clock's date only 3 flights were free and 139 frozen; the
    window holds the next day, so the recovery is the real size of the disruption."""
    late = load_schedule(DATA, KRAKATAU_NOW)
    assert late.day.isoformat() == "2026-09-05"
    found = describe_disruption(late, krakatau_closures(), now=KRAKATAU_NOW, policy=POLICY)
    assert found.free_flights >= 100
    assert len(found.blocked_flights) >= 24
    assert {key.split("/")[1] for key in found.blocked_flights} == {"05SEP", "06SEP"}
    scenario = solve_recovery(
        late,
        krakatau_closures(),
        now=KRAKATAU_NOW,
        policy=POLICY,
        airports=AIRPORTS,
    )
    assert scenario.status in (SolveStatus.OPTIMAL, SolveStatus.FEASIBLE)
    assert scenario.solve_ms <= RULES.solve_time_limit_s.value * 1000
    assert scenario.totals is not None
    assert scenario.totals.free_flights == found.free_flights
    assert scenario.totals.cancelled_flights + scenario.totals.delayed_flights >= 24
    keys = [a.flight_key for a in scenario.actions]
    assert len(set(keys)) == len(keys)
    assert all(
        a.flight_key == f"{a.flight_no}/{a.service_date:%d%b}".upper() for a in scenario.actions
    )
    check_plan(late, scenario, now=KRAKATAU_NOW)


def test_a_flight_that_cannot_fly_inside_the_delay_limit_makes_no_plan(schedule: Schedule) -> None:
    """The solver says why it found nothing; there is no greedy stand-in."""
    blocked = describe_disruption(
        schedule, notam_closures(), now=NOW, policy=POLICY
    ).blocked_flights
    scenario = solve_recovery(
        schedule,
        notam_closures(),
        now=NOW,
        policy=POLICY,
        airports=AIRPORTS,
        protect_flights=blocked[:1],
        max_delay_min=30,
    )
    assert scenario.status is SolveStatus.NO_PLAN
    assert scenario.solver_status == "INFEASIBLE"
    assert scenario.totals is None
    assert scenario.actions == []


def test_a_shorter_delay_limit_cancels_what_it_cannot_delay(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    limit = 60
    scenario = solve_recovery(
        schedule, notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS, max_delay_min=limit
    )
    assert scenario.max_delay_min == limit
    assert all(a.delay_min <= limit for a in scenario.actions)
    check_plan(schedule, scenario)


def test_no_closure_means_nothing_to_change(schedule: Schedule) -> None:
    scenario = solve_recovery(
        schedule, [], now=NOW + timedelta(hours=12), policy=POLICY, airports=AIRPORTS
    )
    assert scenario.status is SolveStatus.OPTIMAL
    assert scenario.actions == []
    assert scenario.totals is not None
    assert scenario.totals.total_usd == 0


def tiny_schedule(*, idle_aircraft_at_sub: bool) -> Schedule:
    """RFA-T01 stands at CGK with two unpaired flights: CGK-SUB at 10:00 and SUB-DPS at 15:00
    (local). With ``idle_aircraft_at_sub``, RFA-T02 landed at SUB at 07:40 and has nothing
    more to do."""
    header = ScheduleHeader(
        label="fictional",
        seed=1,
        anchor_utc_offset_h=7,
        cruise_kt=430,
        overhead_min=30,
        generated_by="test",
    )
    names = ("RFA-T01", "RFA-T02") if idle_aircraft_at_sub else ("RFA-T01",)
    tails = [
        RfaTail(tail=name, type="A320", seats=180, home_base="WIII", crew_id=f"C{n}")
        for n, name in enumerate(names, 1)
    ]
    crews = [
        RfaCrew(crew_id=f"C{n}", base="WIII", report_min=240) for n in range(1, len(names) + 1)
    ]

    def flight(no: int, origin: str, dest: str, std: int, block: int, tail: str) -> RfaFlight:
        return RfaFlight(
            flight_no=f"RFA{no}",
            origin=origin,
            dest=dest,
            std_min=std,
            service_date=NOW.date(),
            day_offset=0,
            block_min=block,
            tail=tail,
            pax_booked=150,
        )

    flights = [
        flight(801, "WIII", "WARR", 600, 90, "RFA-T01"),
        flight(802, "WARR", "WADD", 900, 60, "RFA-T01"),
    ]
    if idle_aircraft_at_sub:
        flights.append(flight(803, "WADD", "WARR", 400, 60, "RFA-T02"))
    return Schedule(day=NOW.date(), header=header, tails=tails, crews=crews, flights=flights)


def solve_tiny(schedule: Schedule) -> RecoveryScenario:
    """CGK is closed from 09:00 to 11:00 and no flight may wait more than 30 minutes."""
    closure = Closure(
        icao=CGK, start=schedule.at(540), end=schedule.at(660), reason="TEST", source_ids=[]
    )
    return solve_recovery(
        schedule,
        [closure],
        now=schedule.at(500),
        policy=POLICY,
        airports=AIRPORTS,
        max_delay_min=30,
    )


def test_a_flight_whose_aircraft_is_stuck_moves_to_one_that_is_at_hand() -> None:
    schedule = tiny_schedule(idle_aircraft_at_sub=True)
    scenario = solve_tiny(schedule)
    assert scenario.status is SolveStatus.OPTIMAL
    by_flight = {a.flight_key: a for a in scenario.actions}
    assert by_flight["RFA801/07SEP"].kind is RecoveryActionKind.CANCEL
    assert by_flight["RFA802/07SEP"].kind is RecoveryActionKind.SWAP
    assert by_flight["RFA802/07SEP"].new_tail == "RFA-T02"
    assert scenario.ferry_legs == []
    assert scenario.totals is not None
    assert scenario.totals.swap_usd == RULES.swap_cost_usd.value
    check_plan(schedule, scenario, now=schedule.at(500))


def test_without_an_aircraft_at_hand_the_stuck_one_is_ferried_to_the_next_flight() -> None:
    schedule = tiny_schedule(idle_aircraft_at_sub=False)
    scenario = solve_tiny(schedule)
    assert scenario.status is SolveStatus.OPTIMAL
    assert {a.flight_key for a in scenario.actions} == {"RFA801/07SEP"}
    (leg,) = scenario.ferry_legs
    assert (leg.tail, leg.origin, leg.dest) == ("RFA-T01", CGK, "WARR")
    assert schedule.minutes_of(leg.dep) >= 500  # not before now
    assert scenario.totals is not None
    assert scenario.totals.ferry_usd == leg.block_min * RULES.ferry_cost_per_block_min_usd.value
    check_plan(schedule, scenario, now=schedule.at(500))


def test_the_solver_reads_its_costs_from_the_policy(
    schedule: Schedule, demo: dict[int, RecoveryScenario]
) -> None:
    data = POLICY.model_dump(mode="json")
    data["recovery"]["cancel_cost_fixed_usd"]["value"] = 1_000_000
    dear = OperatorPolicy.model_validate(data)
    scenario = solve_recovery(schedule, notam_closures(), now=NOW, policy=dear, airports=AIRPORTS)
    base, dearer = demo[0].totals, scenario.totals
    assert base is not None
    assert dearer is not None
    assert dearer.cancelled_flights < base.cancelled_flights
    assert dearer.delay_min > base.delay_min


# --- the checks on a recommendation -------------------------------------------------------------


@pytest.fixture(scope="module")
def solved(schedule: Schedule, demo: dict[int, RecoveryScenario]) -> Toolbox:
    box = Toolbox(schedule, notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS)
    box.disruption()
    for scenario in demo.values():
        box.scenarios[scenario.id] = scenario
        box.evidence.append(box._summary(scenario).__repr__().replace("'", '"'))
    box.compare(list(box.scenarios))
    return box


def verdict(box: Toolbox, text: str, scenario: str | None = None) -> list[str]:
    first = next(iter(box.scenarios))
    return validate_recommendation(
        Recommendation(scenario_id=scenario or first, rationale=text),
        scenarios=box.scenarios,
        evidence="\n".join(box.evidence),
        airports=AIRPORTS,
    )


def test_a_rationale_made_of_tool_figures_passes(solved: Toolbox) -> None:
    first = next(iter(solved.scenarios.values()))
    assert first.totals is not None
    text = (
        f"{first.id} cancels {first.totals.cancelled_flights} flights and costs"
        f" {first.totals.total_usd} USD; CGK reopens at 11:00Z."
    )
    assert verdict(solved, text) == []


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        (
            "The plan saves 7777 USD against the alternative.",
            "NUMBERS NOT IN THE TOOL RESULTS: 7777",
        ),
        ("CGK reopens at 04:07Z, so the plan holds.", "times 4:07"),
        ("RFA999 is cancelled by the plan, which is fine.", "flight RFA999"),
        ("RFA-T99 is stranded at the closed airport now.", "aircraft RFA-T99"),
        ("The plan diverts everything to WXYZ instead.", "airports WXYZ"),
        ("Scenario SC-000000000000 is the plan to use now.", "scenario SC-000000000000"),
        ("Too short", "20 to 700 characters"),
    ],
)
def test_a_rationale_that_invents_something_is_rejected(
    solved: Toolbox, text: str, fragment: str
) -> None:
    problems = verdict(solved, text)
    assert any(fragment in problem for problem in problems), problems


def test_an_unknown_or_unsolved_scenario_cannot_be_recommended(solved: Toolbox) -> None:
    assert any(
        "UNKNOWN SCENARIO" in p
        for p in verdict(solved, "A fine plan with no figures in it.", "SC-bad")
    )
    broken = {
        "SC-aaaaaaaaaaaa": RecoveryScenario(
            id="SC-aaaaaaaaaaaa",
            label="X",
            extend_min=0,
            max_delay_min=1,
            status=SolveStatus.NO_PLAN,
            solver_status="INFEASIBLE",
            solve_ms=1,
            closures=[],
        )
    }
    problems = validate_recommendation(
        Recommendation(scenario_id="SC-aaaaaaaaaaaa", rationale="A fine plan with no figures."),
        scenarios=broken,
        evidence="",
        airports=AIRPORTS,
    )
    assert any("HAS NO PLAN" in p for p in problems)


def test_risks_are_checked_like_the_rationale(solved: Toolbox) -> None:
    first = next(iter(solved.scenarios))
    problems = validate_recommendation(
        Recommendation(
            scenario_id=first,
            rationale="A plain plan that quotes nothing at all here.",
            risks=["Another 4242 flights may go."],
        ),
        scenarios=solved.scenarios,
        evidence="\n".join(solved.evidence),
        airports=AIRPORTS,
    )
    assert any(p.startswith("risk 1") and "4242" in p for p in problems)


async def test_the_tools_refuse_bad_arguments_and_cap_the_scenarios(schedule: Schedule) -> None:
    box = Toolbox(schedule, notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS)
    assert "error" in await box.run_scenario(-5)
    assert "error" in await box.run_scenario(RULES.scenario_extend_2_min.value + 5)
    assert "error" in await box.run_scenario(0, ["RFA000"])
    assert "error" in await box.run_scenario(0, None, RULES.max_delay_min.value + 5)
    assert "error" in box.compare(["SC-none"])
    assert box.submit("SC-none", "x", None)["accepted"] is False


# --- the agent ----------------------------------------------------------------------------------

Turn = list[types.Part] | Exception | Callable[[LlmRequest], list[types.Part]]
_SCRIPT: list[Turn] = []
_CALLS: list[LlmRequest] = []


class ScriptedLlm(BaseLlm):
    patterns: ClassVar[list[str]] = [r"tephra-recovery-scripted"]

    @classmethod
    def supported_models(cls) -> list[str]:
        return cls.patterns

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        _CALLS.append(llm_request)
        turn = _SCRIPT.pop(0) if _SCRIPT else [types.Part(text="DONE")]
        if isinstance(turn, Exception):
            raise turn
        parts = turn(llm_request) if callable(turn) else turn
        yield LlmResponse(content=types.Content(role="model", parts=parts))


LLMRegistry.register(ScriptedLlm)


@pytest.fixture(autouse=True)
def script() -> Iterator[list[Turn]]:
    _SCRIPT.clear()
    _CALLS.clear()
    yield _SCRIPT
    _SCRIPT.clear()


class GeminiStandIn:
    """Only what the recovery agent reads from a non-stub backend: name, ids and budget."""

    def __init__(self, *, budget_left: bool = True) -> None:
        self.name: LlmBackendName = "gemini"
        self._budget_left = budget_left

    def model_id(self, tier: str) -> str:
        return "gemini-test-lite"

    def reserve(self, tier: str) -> bool:
        return self._budget_left

    def exhaust(self, tier: str) -> None:
        self._budget_left = False

    async def structured(self, **_: Any) -> Any:
        raise AssertionError("the recovery agent never makes a structured call")


def call(name: str, **args: Any) -> list[types.Part]:
    return [types.Part(function_call=types.FunctionCall(name=name, args=args))]


def responses(request: LlmRequest, name: str) -> list[dict[str, Any]]:
    found = []
    for content in request.contents:
        for part in content.parts or []:
            if part.function_response is not None and part.function_response.name == name:
                found.append(dict(part.function_response.response or {}))
    return found


def scenario_ids(request: LlmRequest) -> list[str]:
    return [r["scenario_id"] for r in responses(request, "run_scenario") if "scenario_id" in r]


def compare_turn(request: LlmRequest) -> list[types.Part]:
    return call("compare", scenario_ids=scenario_ids(request))


def submit_turn(request: LlmRequest) -> list[types.Part]:
    rows = responses(request, "compare")[-1]["scenarios"]
    first = rows[0]
    text = (
        f"{first['scenario_id']} cancels {first['cancelled_flights']} flights for"
        f" {first['total_usd']} USD."
    )
    return call(
        "submit_recommendation",
        scenario_id=first["scenario_id"],
        rationale=text,
        risks=["The closure may be extended again."],
    )


def bad_submit_turn(request: LlmRequest) -> list[types.Part]:
    ids = scenario_ids(request)
    return call(
        "submit_recommendation",
        scenario_id=ids[0],
        rationale="The plan costs 123456789 USD and is the cheapest.",
    )


def good_run() -> list[Turn]:
    extends = (0, RULES.scenario_extend_1_min.value, RULES.scenario_extend_2_min.value)
    return [
        call("disruption"),
        *[call("run_scenario", extend_min=e) for e in extends],
        compare_turn,
        submit_turn,
        [types.Part(text="Submitted.")],
    ]


async def recommend(
    llm: Any, *, trace: list[TraceEvent] | None = None, model: str = SCRIPTED_MODEL
) -> RecoveryPlan:
    settings = Settings(_env_file=None, model_lite=model)
    schedule = load_schedule(DATA, NOW)
    return await recommend_recovery(
        schedule,
        notam_closures(),
        llm,
        settings=settings,
        policy=POLICY,
        airports=AIRPORTS,
        replay=True,
        trace=trace.append if trace is not None else None,
    )


async def test_the_agent_runs_the_scenarios_and_drafts_a_recommendation(script: list[Turn]) -> None:
    script += good_run()
    trace: list[TraceEvent] = []
    plan = await recommend(GeminiStandIn(), trace=trace)
    assert plan.status == "DRAFT"
    assert plan.outcome == "ACCEPTED"
    assert plan.replay
    assert plan.llm_backend == "gemini"
    assert plan.model_id == "gemini-test-lite"
    assert [r.name for r in plan.tool_calls] == [
        "disruption",
        "run_scenario",
        "run_scenario",
        "run_scenario",
        "compare",
        "submit_recommendation",
    ]
    assert [s.extend_min for s in plan.scenarios] == [0, 180, 360]
    assert plan.chosen is not None
    assert plan.chosen.extend_min == 0
    assert plan.rationale is not None
    assert plan.rationale.startswith("SC-")
    assert plan.risks == ["The closure may be extended again."]
    assert plan.disruption is not None
    assert plan.disruption.blocked_flights
    assert {event.actor for event in trace} == {"adk"}
    assert all(event.stage.value == "RECOVERY" for event in trace)
    assert str(_CALLS[0].config.system_instruction).startswith("# TEPHRA Recovery Planner")


async def test_a_rationale_with_an_invented_figure_gets_one_repair_turn(script: list[Turn]) -> None:
    run = good_run()
    script += [
        *run[:5],
        bad_submit_turn,
        [types.Part(text="Submitted.")],
        submit_turn,
        [types.Part(text="Done.")],
    ]
    trace: list[TraceEvent] = []
    plan = await recommend(GeminiStandIn(), trace=trace)
    assert plan.status == "DRAFT"
    assert plan.outcome == "REPAIRED"
    assert any("REPAIR" in event.message for event in trace)


async def test_a_rationale_still_wrong_after_the_repair_is_ai_unavailable(
    script: list[Turn],
) -> None:
    run = good_run()
    script += [
        *run[:5],
        bad_submit_turn,
        [types.Part(text="Submitted.")],
        bad_submit_turn,
        [types.Part(text="Done.")],
    ]
    trace: list[TraceEvent] = []
    plan = await recommend(GeminiStandIn(), trace=trace)
    assert plan.status == "AI_UNAVAILABLE"
    assert plan.outcome == "MODEL_FAILED"
    assert plan.unavailable_reason is not None
    assert plan.unavailable_reason.startswith("AI UNAVAILABLE: ")
    assert plan.chosen_scenario_id is None
    assert plan.rationale is None
    assert plan.scenarios == []
    assert "123456789" in " ".join(plan.validation_errors)
    assert any("AI UNAVAILABLE" in e.message and e.level == "error" for e in trace)


async def test_a_model_error_is_ai_unavailable_and_keeps_the_tool_calls(script: list[Turn]) -> None:
    script += [call("disruption"), RuntimeError("model unavailable")]
    plan = await recommend(GeminiStandIn())
    assert plan.status == "AI_UNAVAILABLE"
    assert [r.name for r in plan.tool_calls] == ["disruption"]
    assert plan.validation_errors == ["RECOVERY AGENT ERROR: RuntimeError"]


async def test_an_exhausted_budget_stops_before_any_model_call(script: list[Turn]) -> None:
    script += good_run()
    plan = await recommend(GeminiStandIn(budget_left=False))
    assert _CALLS == []
    assert plan.status == "AI_UNAVAILABLE"
    assert "budget_exhausted" in plan.validation_errors


async def test_a_looping_model_is_stopped_by_the_turn_limit(script: list[Turn]) -> None:
    script += [call("disruption") for _ in range(40)]
    plan = await recommend(GeminiStandIn())
    assert len(_CALLS) == 16
    assert plan.status == "AI_UNAVAILABLE"
    assert any("TURN LIMIT" in p for p in plan.validation_errors)


async def test_a_bad_tool_argument_goes_back_to_the_model(script: list[Turn]) -> None:
    run = good_run()
    script += [call("run_scenario", extend_min="soon"), *run]
    plan = await recommend(GeminiStandIn())
    assert plan.status == "DRAFT"
    assert "error" in plan.tool_calls[0].result_summary


async def test_the_stub_backend_recommends_the_published_closure_and_says_no_model() -> None:
    from tephra.agents.llm import StubBackend

    plan = await recommend(StubBackend())
    assert plan.status == "DRAFT"
    assert plan.outcome == "STUB"
    assert plan.llm_backend == "stub"
    assert plan.rationale is not None
    assert plan.rationale.startswith("NO MODEL:")
    assert plan.chosen is not None
    assert plan.chosen.extend_min == 0
    assert [s.extend_min for s in plan.scenarios] == [0, 180, 360]


def test_the_recovery_prompt_matches_the_tools_the_agent_has() -> None:
    import inspect
    import re

    box = Toolbox(
        load_schedule(DATA, NOW), notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS
    )
    tools = {
        tool.__name__: list(inspect.signature(tool).parameters)
        for tool in build_recovery_agent(SCRIPTED_MODEL, box).tools
        if callable(tool)
    }
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    named: dict[str, set[str]] = {}
    for name, args in re.findall(r"`([a-z_]+)\(([a-z_, ]*)\)`", prompt):
        named.setdefault(name, set()).add(args)
    assert set(named) == set(tools)
    for name, spellings in named.items():
        for args in spellings - {""}:
            assert [a.strip() for a in args.split(",")] == tools[name], name


def test_the_recovery_agent_runs_gemini_3_at_temperature_one() -> None:
    box = Toolbox(
        load_schedule(DATA, NOW), notam_closures(), now=NOW, policy=POLICY, airports=AIRPORTS
    )
    config = build_recovery_agent("gemini-3.5-flash-lite", box).generate_content_config
    assert config is not None
    assert config.temperature == 1.0


# --- the plan state machine -----------------------------------------------------------------------


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    opened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield opened
    await opened.aclose()


async def draft(**changes: Any) -> RecoveryPlan:
    from tephra.agents.llm import StubBackend

    plan = await recommend(StubBackend())
    return plan.model_copy(update=changes)


async def test_a_draft_is_stored_audited_and_published(store: SqliteStore) -> None:
    bus = EventBus()
    queue = bus.subscribe()
    plan = await decisions.submit_plan(store, bus, await draft())
    assert (await store.get(Collection.RECOVERY, plan.id)) is not None
    entries = await audit.list_entries(store)
    assert [e.action for e in entries] == [AuditAction.RECOVERY_PROPOSED]
    assert entries[0].after is not None
    assert entries[0].after["status"] == "DRAFT"
    event = await queue.get(1)
    assert event is not None
    assert event.name == SseEvent.RECOVERY
    assert event.data["id"] == plan.id


async def test_approving_moves_the_draft_once_with_a_version_check(store: SqliteStore) -> None:
    bus = EventBus()
    plan = await decisions.submit_plan(store, bus, await draft())
    with pytest.raises(decisions.VersionConflict):
        await decisions.approve(store, bus, plan.id, expected_version=7, actor="desk:Ana")
    approved = await decisions.approve(store, bus, plan.id, expected_version=1, actor="desk:Ana")
    assert approved.status == "APPROVED"
    assert approved.version == 2
    assert approved.decided_by == "desk:Ana"
    assert approved.decided_at is not None
    with pytest.raises(decisions.InvalidTransition):
        await decisions.reject(store, bus, plan.id, expected_version=2, reason="late", actor="x")
    entries = await audit.list_entries(store)
    assert entries[0].action is AuditAction.RECOVERY_DECIDED
    assert await audit.verify_chain(store) == []
    assert await store.list_docs(Collection.OUTBOUND) == []


async def test_rejecting_needs_a_reason(store: SqliteStore) -> None:
    bus = EventBus()
    plan = await decisions.submit_plan(store, bus, await draft())
    with pytest.raises(decisions.RejectedInput):
        await decisions.reject(store, bus, plan.id, expected_version=1, reason=" a ", actor="x")
    rejected = await decisions.reject(
        store, bus, plan.id, expected_version=1, reason="Wrong closure end", actor="desk:Ana"
    )
    assert rejected.status == "REJECTED"
    assert rejected.reject_reason == "Wrong closure end"
    with pytest.raises(decisions.PlanNotFound):
        await decisions.approve(store, bus, "REC-missing", expected_version=1, actor="x")


async def test_a_new_draft_retires_the_open_one_of_the_same_mode(store: SqliteStore) -> None:
    bus = EventBus()
    first = await decisions.submit_plan(store, bus, await draft(id="REC-000000000001"))
    other_mode = await decisions.submit_plan(
        store, bus, await draft(id="REC-000000000002", replay=False)
    )
    second = await decisions.submit_plan(store, bus, await draft(id="REC-000000000003"))
    states = {p.id: p.status for p in await decisions.list_plans(store)}
    assert states[first.id] == "SUPERSEDED"
    assert states[other_mode.id] == "DRAFT"
    assert states[second.id] == "DRAFT"
    assert [p.id for p in await decisions.list_plans(store, replay=False)] == [other_mode.id]


async def test_an_unavailable_run_is_stored_audited_as_an_ai_failure_and_cannot_be_decided(
    store: SqliteStore,
) -> None:
    bus = EventBus()
    failed = (await draft()).model_copy(
        update={"status": "AI_UNAVAILABLE", "unavailable_reason": "AI UNAVAILABLE: test"}
    )
    await decisions.submit_plan(store, bus, failed)
    entries = await audit.list_entries(store)
    assert [e.action for e in entries] == [AuditAction.AI_FAILED]
    assert entries[0].note == "AI UNAVAILABLE: test"
    with pytest.raises(decisions.InvalidTransition):
        await decisions.approve(store, bus, failed.id, expected_version=1, actor="x")


# --- HTTP ---------------------------------------------------------------------------------------


@dataclass(eq=False)
class FakeRuntime:
    settings: Settings
    store: SqliteStore
    llm: Any
    bus: EventBus = field(default_factory=EventBus)
    mode: RunMode = RunMode.REPLAY
    policy: OperatorPolicy = field(default_factory=lambda: POLICY)
    airports: AirportCatalogue = field(default_factory=lambda: CATALOGUE)
    cones: dict[str, HazardCone] = field(default_factory=dict)
    situations: dict[str, Any] = field(default_factory=dict)
    traces: list[str] = field(default_factory=list)

    def trace(self, stage: Any, actor: Any, message: str, **_: Any) -> None:
        self.traces.append(message)


@pytest.fixture
def api(store: SqliteStore) -> Iterator[tuple[TestClient, FakeRuntime]]:
    from tephra.agents.llm import StubBackend

    app = FastAPI()
    app.include_router(router, prefix="/api")
    _install_error_handlers(app)
    runtime = FakeRuntime(
        settings=Settings(_env_file=None, data_dir=DATA), store=store, llm=StubBackend()
    )
    app.state.runtime = runtime
    app.state.settings = runtime.settings
    session = SessionInfo(name="Ana K", expires_at=NOW + timedelta(hours=8))
    app.dependency_overrides[require_desk] = lambda: session
    with TestClient(app) as client:
        yield client, runtime


ENTERED = {
    "closures": [
        {
            "icao": CGK,
            "start": "2026-09-07T01:28:00.000Z",
            "end": "2026-09-07T11:00:00.000Z",
            "reference": "NOTAM A1234/26",
        }
    ]
}


def test_running_without_a_closure_is_a_conflict(api: tuple[TestClient, FakeRuntime]) -> None:
    client, _ = api
    response = client.post("/api/desk/recovery/run", json={})
    assert response.status_code == 409
    assert response.json()["error"] == "no_closure"


def test_a_dispatcher_runs_approves_and_lists_a_plan(api: tuple[TestClient, FakeRuntime]) -> None:
    client, runtime = api
    run = client.post("/api/desk/recovery/run", json=ENTERED)
    assert run.status_code == 200, run.text
    plan = run.json()
    assert plan["status"] == "DRAFT"
    assert plan["label"].startswith("FICTIONAL AIRLINE RFA")
    assert plan["closures"][0]["reason"] == "ENTERED BY DISPATCHER NOTAM A1234/26"
    assert any("RECOVERY" in message or "NO MODEL" in message for message in runtime.traces)
    listed = client.get("/api/recovery").json()["plans"]
    assert [p["id"] for p in listed] == [plan["id"]]
    assert plan["chosen"]["id"] == plan["chosen_scenario_id"]  # the API returns the scenario
    assert listed[0]["chosen"] == plan["chosen"]
    assert plan["chosen"]["actions"][0]["flight_key"].startswith("RFA")
    stored = asyncio.run(runtime.store.get(Collection.RECOVERY, plan["id"]))
    assert stored is not None
    assert "chosen" not in stored  # derived, so not stored twice
    approved = client.post(f"/api/desk/recovery/{plan['id']}/approve", json={"version": 1})
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    again = client.post(f"/api/desk/recovery/{plan['id']}/approve", json={"version": 2})
    assert again.status_code == 409
    assert again.json()["error"] == "invalid_transition"


def test_a_stale_version_and_a_bad_id_are_refused(api: tuple[TestClient, FakeRuntime]) -> None:
    client, _ = api
    plan = client.post("/api/desk/recovery/run", json=ENTERED).json()
    stale = client.post(
        f"/api/desk/recovery/{plan['id']}/reject", json={"version": 9, "reason": "wrong end"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"] == "version_conflict"
    short = client.post(
        f"/api/desk/recovery/{plan['id']}/reject", json={"version": 1, "reason": "x"}
    )
    assert short.status_code == 422
    assert client.post("/api/desk/recovery/nope/approve", json={"version": 1}).status_code == 404
    missing = client.post("/api/desk/recovery/REC-000000000000/approve", json={"version": 1})
    assert missing.status_code == 404


def test_a_bad_dispatcher_closure_is_refused(api: tuple[TestClient, FakeRuntime]) -> None:
    client, _ = api
    wrong = {"closures": [{**ENTERED["closures"][0], "icao": "KJFK"}]}
    assert client.post("/api/desk/recovery/run", json=wrong).status_code == 422
    backwards = {"closures": [{**ENTERED["closures"][0], "end": "2026-09-07T00:00:00.000Z"}]}
    assert client.post("/api/desk/recovery/run", json=backwards).status_code == 422
    sneaky = {"closures": [{**ENTERED["closures"][0], "reference": "<script>"}]}
    assert client.post("/api/desk/recovery/run", json=sneaky).status_code == 422


def test_a_failed_model_answers_503_with_ai_unavailable_and_stores_the_record(
    api: tuple[TestClient, FakeRuntime],
) -> None:
    client, runtime = api
    runtime.llm = GeminiStandIn(budget_left=False)
    runtime.settings = Settings(_env_file=None, data_dir=DATA, model_lite=SCRIPTED_MODEL)
    response = client.post("/api/desk/recovery/run", json=ENTERED)
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "ai_unavailable"
    assert body["message"].startswith("AI UNAVAILABLE: ")
    stored = client.get("/api/recovery").json()["plans"]
    assert stored[0]["status"] == "AI_UNAVAILABLE"
    assert stored[0]["rationale"] is None
