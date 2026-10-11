"""The recovery model: re-plan the day's flights around airport closures with CP-SAT.

Each flight the solver may change is kept (possibly delayed in 5-minute steps up to the
policy's limit), cancelled together with the other leg of its excursion, or moved to another
aircraft. Aircraft are chains of flights found by one multi-route circuit constraint: a
chain starts where the aircraft stands now, every hop lands where the next flight starts and
leaves the minimum turn, and a hop between different airports is a ferry flight with its own
cost. A crew's flight duty period, seat counts, and closed airports (no departure and no
arrival while closed) are constraints. The objective is the policy's USD weights.

Only flights that have not left (and are not about to) and depart before the horizon are
free. The first flight of each aircraft after the horizon stays as published, so every chain
has to reach it. There is no heuristic plan: when CP-SAT finds none, the scenario is
``NO_PLAN`` and says why.
"""

import math
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Final

from ortools.sat.python import cp_model

from tephra.geo.units import distance_nm
from tephra.models import Airport, OperatorPolicy
from tephra.recovery.models import (
    MINUTES_PER_DAY,
    Closure,
    Disruption,
    FerryLeg,
    FlightAction,
    RecoveryActionKind,
    RecoveryScenario,
    RecoveryTotals,
    RfaFlight,
    Schedule,
    SolveStatus,
)
from tephra.recovery.schedule import block_minutes
from tephra.util.hashing import sha256_json, stable_id

__all__ = ["DELAY_STEP_MIN", "describe_disruption", "solve_recovery"]

DELAY_STEP_MIN: Final = 5
SUCCESSOR_WINDOW_MIN: Final = 180
"""Prunes the arc set: a flight is offered as the next one of an aircraft only when it leaves
at most this long after the aircraft is ready, unless it is the aircraft's published next
flight."""
FERRIES_PER_FLIGHT: Final = 2
"""Ferry hops offered after each flight: the ones that arrive soonest before a departure."""
SEARCH_WORKERS: Final = 8
"""Fixed, not the CPU count: interleaved search is reproducible only for one worker count."""
SEARCH_SEED: Final = 7
STOP_MARGIN_S: Final = 0.1
"""The policy's time limit covers building the model and the solver's own stop latency, so the
search gets the limit minus the time already spent minus this much."""
MIN_SEARCH_S: Final = 0.2
_PER_HOUR: Final = 60
"""Objective terms are scaled by 60 so that a cost per passenger-hour stays an integer."""
_Window = tuple[int, int]


# --- the instance ----------------------------------------------------------------------------


@dataclass
class _Frame:
    """Who is free, who is frozen and where every aircraft stands, in minutes after the anchor."""

    schedule: Schedule
    windows: dict[str, list[_Window]]
    now_min: int
    horizon_end_min: int
    free: list[RfaFlight] = field(default_factory=list)
    pinned: list[RfaFlight] = field(default_factory=list)
    frozen: int = 0
    kept_pairs: set[tuple[str, date]] = field(default_factory=set)
    """Excursions with a leg after the horizon: that leg stays as published, so the other
    leg cannot be cancelled."""
    tail_loc: list[str | None] = field(default_factory=list)
    tail_ready: list[int | None] = field(default_factory=list)

    def closed(self, icao: str, minute: float) -> bool:
        return any(start <= minute < end for start, end in self.windows.get(icao, ()))

    def blocked(self, flight: RfaFlight) -> bool:
        return self.closed(flight.origin, flight.std_min) or self.closed(
            flight.dest, flight.std_min + flight.block_min
        )


def _windows(schedule: Schedule, closures: Iterable[Closure]) -> dict[str, list[_Window]]:
    result: dict[str, list[_Window]] = defaultdict(list)
    for closure in closures:
        start = math.floor(schedule.minutes_of(closure.start))
        end = math.ceil(schedule.minutes_of(closure.end))
        result[closure.icao].append((start, end))
    return result


def _frame(
    schedule: Schedule, closures: Sequence[Closure], now: datetime, policy: OperatorPolicy
) -> _Frame:
    rules = policy.recovery
    now_min = schedule.minutes_of(now)
    ends = [schedule.minutes_of(closure.end) for closure in closures]
    horizon_end = math.ceil(max(ends, default=now_min) + rules.horizon_after_closure_min.value)
    frame = _Frame(schedule, _windows(schedule, closures), math.ceil(now_min), horizon_end)
    chains: dict[str, list[RfaFlight]] = defaultdict(list)
    for flight in schedule.flights:
        chains[flight.tail].append(flight)
    freeze_until = now_min + rules.freeze_window_min.value
    turn = rules.min_turn_min.value
    for tail in schedule.tails:
        chain = chains[tail.tail]
        cut = 0
        while cut < len(chain) and _is_frozen(frame, chain[cut], now_min, freeze_until):
            cut += 1
        frame.frozen += cut
        rest = chain[cut:]
        frame.free += [flight for flight in rest if flight.std_min <= horizon_end]
        beyond = [flight for flight in rest if flight.std_min > horizon_end]
        frame.pinned += beyond[:1]
        frame.kept_pairs |= {
            (flight.pair_id, flight.service_date) for flight in beyond if flight.pair_id
        }
        if cut:
            last = chain[cut - 1]
            frame.tail_loc.append(last.dest)
            frame.tail_ready.append(last.std_min + last.block_min + turn)
        else:
            frame.tail_loc.append(rest[0].origin if rest else None)
            frame.tail_ready.append(None)
    return frame


def _is_frozen(frame: _Frame, flight: RfaFlight, now_min: float, freeze_until: float) -> bool:
    """Departed, or leaving within the freeze window and not stopped by a closure."""
    if flight.std_min < now_min:
        return True
    return flight.std_min < freeze_until and not frame.blocked(flight)


def describe_disruption(
    schedule: Schedule, closures: Sequence[Closure], *, now: datetime, policy: OperatorPolicy
) -> Disruption:
    frame = _frame(schedule, closures, now, policy)
    now_min = schedule.minutes_of(now)
    blocked = [f for f in schedule.flights if f.std_min >= now_min and frame.blocked(f)]
    airborne = [
        f
        for f in schedule.flights
        if f.std_min < now_min < f.std_min + f.block_min
        and frame.closed(f.dest, f.std_min + f.block_min)
    ]
    return Disruption(
        closures=list(closures),
        blocked_flights=[f.key for f in blocked],
        blocked_pax=sum(f.pax_booked for f in blocked),
        airborne_at_risk=[f.key for f in airborne],
        free_flights=len(frame.free),
        frozen_flights=frame.frozen,
        horizon_end=schedule.at(frame.horizon_end_min),
    )


# --- the model ---------------------------------------------------------------------------------


@dataclass
class _Node:
    flight: RfaFlight
    index: int
    orig_tail: int
    latest: int
    st: cp_model.IntVar
    tail: cp_model.IntVar
    skip: cp_model.IntVar | None = None
    moved: cp_model.IntVar | None = None

    @property
    def pinned(self) -> bool:
        return self.skip is None


@dataclass
class _Ferry:
    lit: cp_model.IntVar
    tail: cp_model.IntVar
    origin: str
    dest: str
    dep: cp_model.IntVar
    block_min: int


class _Model:
    def __init__(
        self,
        frame: _Frame,
        policy: OperatorPolicy,
        airports: Mapping[str, Airport],
        *,
        protect: frozenset[str],
        max_delay_min: int,
    ) -> None:
        self.frame = frame
        self.rules = policy.recovery
        self.airports = airports
        self.protect = protect
        self.max_delay_min = max_delay_min
        self.model = cp_model.CpModel()
        self.arcs: list[tuple[int, int, cp_model.IntVar]] = []
        self.terms: list[tuple[int, cp_model.IntVar]] = []
        self.offset = 0
        self.ferries: list[_Ferry] = []
        self.starts: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        self.first_lits: dict[tuple[int, int], cp_model.IntVar] = {}
        schedule = frame.schedule
        self.tail_index = {tail.tail: i for i, tail in enumerate(schedule.tails)}
        reports = {crew.crew_id: crew.report_min for crew in schedule.crews}
        self.duty_limits = [
            reports[tail.crew_id] + self.rules.max_fdp_min.value for tail in schedule.tails
        ]
        self.nodes: list[_Node] = []
        for flight in frame.free:
            self.nodes.append(self._node(flight, pinned=False))
        for flight in frame.pinned:
            self.nodes.append(self._node(flight, pinned=True))
        self._link_pairs()
        self._add_arcs()
        self._close()

    # variables and per-flight constraints

    def _node(self, flight: RfaFlight, *, pinned: bool) -> _Node:
        model = self.model
        index = len(self.nodes) + 1
        orig = self.tail_index[flight.tail]
        if pinned:
            st = model.NewIntVar(flight.std_min, flight.std_min, f"st{index}")
            tail = model.NewIntVar(orig, orig, f"tail{index}")
            return _Node(flight, index, orig, flight.std_min, st, tail)
        starts = self._start_times(flight)
        domain = cp_model.Domain.FromValues(sorted({*starts, flight.std_min}))
        st = model.NewIntVarFromDomain(domain, f"st{index}")
        seats = [k for k, t in enumerate(self.frame.schedule.tails) if t.seats >= flight.pax_booked]
        tail = model.NewIntVarFromDomain(cp_model.Domain.FromValues(seats), f"tail{index}")
        skip = model.NewBoolVar(f"skip{index}")
        node = _Node(flight, index, orig, max(starts, default=flight.std_min), st, tail, skip)
        self.arcs.append((index, index, skip))
        model.Add(st == flight.std_min).OnlyEnforceIf(skip)
        model.Add(tail == orig).OnlyEnforceIf(skip)
        if flight.std_min not in starts:
            model.Add(st != flight.std_min).OnlyEnforceIf(skip.Not())
        if flight.key in self.protect:
            model.Add(skip == 0)
        limit = model.NewIntVar(min(self.duty_limits), max(self.duty_limits), f"limit{index}")
        model.AddElement(tail, self.duty_limits, limit)
        shift = flight.day_offset * MINUTES_PER_DAY
        model.Add(st + flight.block_min <= limit + shift).OnlyEnforceIf(skip.Not())
        if len(seats) > 1:
            node.moved = model.NewBoolVar(f"moved{index}")
            model.Add(tail == orig).OnlyEnforceIf(node.moved.Not())
            model.Add(tail != orig).OnlyEnforceIf(node.moved)
        self._flight_costs(node, skip)
        return node

    def _start_times(self, flight: RfaFlight) -> set[int]:
        """Departure times, in delay steps, at which neither end of the flight is closed."""
        closed = self.frame.closed
        steps = range(self.max_delay_min // DELAY_STEP_MIN + 1)
        times = (flight.std_min + DELAY_STEP_MIN * step for step in steps)
        return {
            t
            for t in times
            if not closed(flight.origin, t) and not closed(flight.dest, t + flight.block_min)
        }

    def _flight_costs(self, node: _Node, skip: cp_model.IntVar) -> None:
        rules = self.rules
        flight = node.flight
        per_min = _PER_HOUR * rules.delay_cost_per_min_usd.value
        per_min += flight.pax_booked * rules.delay_cost_per_pax_hour_usd.value
        self.terms.append((per_min, node.st))
        self.offset -= per_min * flight.std_min
        cancel = flight.pax_booked * rules.cancel_cost_per_pax_usd.value
        self.terms.append((_PER_HOUR * (cancel + rules.cancel_cost_fixed_usd.value), skip))
        if node.moved is not None:
            self.terms.append((_PER_HOUR * rules.swap_cost_usd.value, node.moved))

    def _link_pairs(self) -> None:
        """Both legs of an excursion are flown or both are cancelled."""
        first: dict[tuple[str, date], cp_model.IntVar] = {}
        for node in self.nodes:
            if node.skip is None or node.flight.pair_id is None:
                continue
            pair = (node.flight.pair_id, node.flight.service_date)
            if pair in self.frame.kept_pairs:
                self.model.Add(node.skip == 0)
            other = first.setdefault(pair, node.skip)
            if other is not node.skip:
                self.model.Add(node.skip == other)

    # arcs of the circuit

    def _add_arcs(self) -> None:
        turn = self.rules.min_turn_min.value
        by_origin: dict[str, list[_Node]] = defaultdict(list)
        for node in self.nodes:
            by_origin[node.flight.origin].append(node)
        for node in self.nodes:
            self._start_arcs(node)
            self._end_arc(node)
            if node.pinned:
                continue
            for follower in by_origin[node.flight.dest]:
                if self._can_follow(node, follower, turn):
                    self._hop(node, follower, turn)
            self._ferry_hops(node, turn)
        for k in range(len(self.frame.schedule.tails)):
            self._ferry_starts(k, turn)

    def _can_follow(self, node: _Node, follower: _Node, turn: int) -> bool:
        ready = node.flight.std_min + node.flight.block_min + turn
        if follower.index == node.index or follower.latest < ready:
            return False
        near = follower.flight.std_min - ready <= SUCCESSOR_WINDOW_MIN
        return near or follower.orig_tail == node.orig_tail

    def _start_arcs(self, node: _Node) -> None:
        frame = self.frame
        for k in range(len(frame.schedule.tails)):
            ready = frame.tail_ready[k]
            if frame.tail_loc[k] != node.flight.origin or (node.pinned and k != node.orig_tail):
                continue
            if ready is not None and ready > node.latest:
                continue
            lit = self.model.NewBoolVar(f"start{k}_{node.index}")
            self.arcs.append((0, node.index, lit))
            self.starts[k].append(lit)
            self.first_lits[(k, node.index)] = lit
            self.model.Add(node.tail == k).OnlyEnforceIf(lit)
            if ready is not None:
                self.model.Add(node.st >= ready).OnlyEnforceIf(lit)

    def _end_arc(self, node: _Node) -> None:
        lit = self.model.NewBoolVar(f"end{node.index}")
        self.arcs.append((node.index, 0, lit))
        if node.pinned:
            self.model.Add(lit == 1)

    def _hop(self, node: _Node, follower: _Node, turn: int) -> None:
        lit = self.model.NewBoolVar(f"hop{node.index}_{follower.index}")
        self.arcs.append((node.index, follower.index, lit))
        self.model.Add(follower.tail == node.tail).OnlyEnforceIf(lit)
        self.model.Add(follower.st >= node.st + node.flight.block_min + turn).OnlyEnforceIf(lit)

    def _hop_minutes(self, origin: str, dest: str) -> int | None:
        here, there = self.airports.get(origin), self.airports.get(dest)
        if here is None or there is None:
            return None
        distance = distance_nm(here.lat, here.lon, there.lat, there.lon)
        return block_minutes(distance, self.frame.schedule.header)

    def _ferry_hops(self, node: _Node, turn: int) -> None:
        """Offers after a flight: the ferries that arrive soonest before a departure."""
        flight = node.flight
        ready = flight.std_min + flight.block_min + turn
        offers: list[tuple[int, int, _Node, int]] = []
        for follower in self.nodes:
            hop = self._hop_minutes(flight.dest, follower.flight.origin)
            if hop is None or follower.flight.origin == flight.dest:
                continue
            gap = follower.flight.std_min - (ready + hop + turn)
            if gap >= 0:
                offers.append((gap, follower.index, follower, hop))
        for follower, hop in _chosen_offers(offers, node.orig_tail):
            made = self._ferry(flight.dest, follower, hop, ready, turn)
            if made is None:
                continue
            lit, dep = made
            self.arcs.append((node.index, follower.index, lit))
            self.model.Add(follower.tail == node.tail).OnlyEnforceIf(lit)
            self.model.Add(dep >= node.st + flight.block_min + turn).OnlyEnforceIf(lit)
            self.ferries.append(
                _Ferry(lit, node.tail, flight.dest, follower.flight.origin, dep, hop)
            )

    def _ferry_starts(self, k: int, turn: int) -> None:
        """Offers from where an aircraft stands now, for the case its own flights are gone."""
        frame = self.frame
        here = frame.tail_loc[k]
        if here is None:
            return
        ready = frame.tail_ready[k]
        earliest = frame.now_min if ready is None else max(ready, frame.now_min)
        offers: list[tuple[int, int, _Node, int]] = []
        for follower in self.nodes:
            hop = self._hop_minutes(here, follower.flight.origin)
            if hop is None or follower.flight.origin == here:
                continue
            if follower.pinned and follower.orig_tail != k:
                continue
            gap = follower.flight.std_min - (earliest + hop + turn)
            if gap >= 0:
                offers.append((gap, follower.index, follower, hop))
        for follower, hop in _chosen_offers(offers, k):
            made = self._ferry(here, follower, hop, earliest, turn)
            if made is None:
                continue
            lit, dep = made
            tail = self.model.NewConstant(k)
            self.arcs.append((0, follower.index, lit))
            self.starts[k].append(lit)
            self.model.Add(follower.tail == k).OnlyEnforceIf(lit)
            self.ferries.append(_Ferry(lit, tail, here, follower.flight.origin, dep, hop))

    def _ferry(
        self, origin: str, follower: _Node, hop: int, earliest: int, turn: int
    ) -> tuple[cp_model.IntVar, cp_model.IntVar] | None:
        """A positioning flight before ``follower``, itself kept out of closure windows. The
        caller ties it to the aircraft; this sets its time window, cost and the follower's start."""
        closed = self.frame.closed
        first = -(-earliest // DELAY_STEP_MIN) * DELAY_STEP_MIN
        times = [
            t
            for t in range(first, follower.latest - hop - turn + 1, DELAY_STEP_MIN)
            if not closed(origin, t) and not closed(follower.flight.origin, t + hop)
        ]
        if not times:
            return None
        model = self.model
        name = f"{len(self.ferries)}"
        lit = model.NewBoolVar(f"ferry{name}")
        dep = model.NewIntVarFromDomain(cp_model.Domain.FromValues(times), f"fd{name}")
        model.Add(follower.st >= dep + hop + turn).OnlyEnforceIf(lit)
        self.terms.append((_PER_HOUR * self.rules.ferry_cost_per_block_min_usd.value * hop, lit))
        return lit, dep

    def _close(self) -> None:
        for lits in self.starts.values():
            self.model.AddAtMostOne(lits)
        # The depot of a multi-route circuit needs one route, even when every flight is cancelled.
        sentinel = len(self.nodes) + 1
        present = self.model.NewBoolVar("sentinel")
        self.model.Add(present == 1)
        self.arcs += [(0, sentinel, present), (sentinel, 0, present)]
        self.model.AddMultipleCircuit(self.arcs)
        self.model.Minimize(sum(coef * var for coef, var in self.terms) + self.offset)


def _chosen_offers(
    offers: Sequence[tuple[int, int, _Node, int]], tail: int
) -> list[tuple[_Node, int]]:
    """The ferries that arrive soonest, and always the way to the aircraft's own pinned flight:
    that flight stays as published, so a chain that was displaced has to be able to reach it."""
    ranked = sorted(offers, key=lambda offer: offer[:2])
    soonest = ranked[:FERRIES_PER_FLIGHT]
    own = [o for o in ranked[FERRIES_PER_FLIGHT:] if o[2].pinned and o[2].orig_tail == tail]
    return [(follower, hop) for *_, follower, hop in [*soonest, *own]]


# --- solving and reading the answer ------------------------------------------------------------


def solve_recovery(
    schedule: Schedule,
    closures: Sequence[Closure],
    *,
    now: datetime,
    policy: OperatorPolicy,
    airports: Mapping[str, Airport],
    extend_min: int = 0,
    protect_flights: Iterable[str] = (),
    max_delay_min: int | None = None,
) -> RecoveryScenario:
    """One scenario: the closures as given, each lasting ``extend_min`` minutes longer."""
    started = time.perf_counter()
    rules = policy.recovery
    protect = frozenset(protect_flights)
    delay_limit = min(max_delay_min or rules.max_delay_min.value, rules.max_delay_min.value)
    planned = [
        c.model_copy(update={"end": c.end + timedelta(minutes=extend_min)}) for c in closures
    ]
    frame = _frame(schedule, planned, now, policy)
    ident = stable_id(
        "SC",
        now,
        extend_min,
        sorted(protect),
        delay_limit,
        sha256_json([c.model_dump(mode="json") for c in closures]),
    )
    base = {
        "id": ident,
        "label": "CLOSURE AS FORECAST" if extend_min == 0 else f"CLOSURE +{extend_min} MIN",
        "extend_min": extend_min,
        "protect_flights": sorted(protect),
        "max_delay_min": delay_limit,
        "closures": planned,
    }
    if not frame.free:
        totals = _totals(frame, [], [], policy)
        return RecoveryScenario(
            **base,
            status=SolveStatus.OPTIMAL,
            solver_status="NO_FREE_FLIGHTS",
            solve_ms=_ms(started),
            totals=totals,
        )
    built = _Model(frame, policy, airports, protect=protect, max_delay_min=delay_limit)
    solver = cp_model.CpSolver()
    spent = time.perf_counter() - started
    solver.parameters.max_time_in_seconds = max(
        MIN_SEARCH_S, float(rules.solve_time_limit_s.value) - spent - STOP_MARGIN_S
    )
    # A deterministic limit with interleaved search returns the same plan on every run and
    # every machine (only the wall time differs); the wall-clock limit above is a guard.
    solver.parameters.max_deterministic_time = float(rules.solve_work_s.value)
    solver.parameters.num_workers = SEARCH_WORKERS
    solver.parameters.interleave_search = True
    solver.parameters.random_seed = SEARCH_SEED
    code = solver.Solve(built.model)
    name = solver.StatusName(code)
    if code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return RecoveryScenario(
            **base, status=SolveStatus.NO_PLAN, solver_status=name, solve_ms=_ms(started)
        )
    actions, ferries = _read(built, solver, schedule)
    return RecoveryScenario(
        **base,
        status=SolveStatus(name),
        solver_status=name,
        solve_ms=_ms(started),
        totals=_totals(frame, actions, ferries, policy),
        actions=actions,
        ferry_legs=ferries,
    )


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _read(
    built: _Model, solver: cp_model.CpSolver, schedule: Schedule
) -> tuple[list[FlightAction], list[FerryLeg]]:
    tails = schedule.tails
    actions: list[FlightAction] = []
    for node in built.nodes:
        if node.skip is None:
            continue
        flight = node.flight
        st, tail = solver.Value(node.st), solver.Value(node.tail)
        delay = st - flight.std_min
        if solver.Value(node.skip):
            kind = RecoveryActionKind.CANCEL
        elif tail != node.orig_tail:
            kind = RecoveryActionKind.SWAP
        elif delay > 0:
            kind = RecoveryActionKind.DELAY
        else:
            continue
        cancelled = kind is RecoveryActionKind.CANCEL
        actions.append(
            FlightAction(
                flight_no=flight.flight_no,
                flight_key=flight.key,
                service_date=flight.service_date,
                origin=flight.origin,
                dest=flight.dest,
                std=schedule.at(flight.std_min),
                kind=kind,
                new_std=None if cancelled else schedule.at(st),
                delay_min=0 if cancelled else delay,
                tail=flight.tail,
                new_tail=tails[tail].tail if kind is RecoveryActionKind.SWAP else None,
                pax_booked=flight.pax_booked,
                pair_id=flight.pair_id,
            )
        )
    legs = [
        FerryLeg(
            tail=tails[solver.Value(f.tail)].tail,
            origin=f.origin,
            dest=f.dest,
            dep=schedule.at(solver.Value(f.dep)),
            arr=schedule.at(solver.Value(f.dep) + f.block_min),
            block_min=f.block_min,
        )
        for f in built.ferries
        if solver.Value(f.lit)
    ]
    return sorted(actions, key=lambda a: (a.std, a.flight_key)), sorted(
        legs, key=lambda leg: leg.dep
    )


def _totals(
    frame: _Frame,
    actions: Sequence[FlightAction],
    ferries: Sequence[FerryLeg],
    policy: OperatorPolicy,
) -> RecoveryTotals:
    rules = policy.recovery
    delayed = [a for a in actions if a.delay_min > 0]
    cancelled = [a for a in actions if a.kind is RecoveryActionKind.CANCEL]
    swapped = [a for a in actions if a.kind is RecoveryActionKind.SWAP]
    delay_usd = sum(
        a.delay_min
        * (
            rules.delay_cost_per_min_usd.value
            + a.pax_booked * rules.delay_cost_per_pax_hour_usd.value / _PER_HOUR
        )
        for a in delayed
    )
    cancel_usd = sum(
        a.pax_booked * rules.cancel_cost_per_pax_usd.value + rules.cancel_cost_fixed_usd.value
        for a in cancelled
    )
    swap_usd = len(swapped) * rules.swap_cost_usd.value
    ferry_usd = sum(leg.block_min for leg in ferries) * rules.ferry_cost_per_block_min_usd.value
    pax_delayed = sum(a.pax_booked for a in delayed)
    pax_cancelled = sum(a.pax_booked for a in cancelled)
    parts = [round(delay_usd), cancel_usd, swap_usd, ferry_usd]
    return RecoveryTotals(
        free_flights=len(frame.free),
        kept_flights=len(frame.free) - len({a.flight_key for a in actions}),
        delayed_flights=len(delayed),
        cancelled_flights=len(cancelled),
        swapped_flights=len(swapped),
        ferries=len(ferries),
        delay_min=sum(a.delay_min for a in delayed),
        pax_delayed=pax_delayed,
        pax_cancelled=pax_cancelled,
        pax_affected=pax_delayed + pax_cancelled,
        delay_usd=parts[0],
        cancel_usd=parts[1],
        swap_usd=parts[2],
        ferry_usd=parts[3],
        total_usd=sum(parts),
    )
