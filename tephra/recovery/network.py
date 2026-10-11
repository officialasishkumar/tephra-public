"""The closures that matter to the RFA network, shared by the Desk's run button and the
pipeline's automatic run, and the one lock that lets only one recovery plan be made at a time
(a plan spends the lite model's daily budget)."""

import asyncio
import weakref
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Protocol

from tephra.config import MAX_HORIZON_H
from tephra.feeds.airports import AirportCatalogue
from tephra.models import HazardCone, Metar, OperatorPolicy, Situation, Taf
from tephra.recovery.closures import find_closures
from tephra.recovery.models import Closure, Schedule

__all__ = ["NetworkRuntime", "network_closures", "network_icaos", "run_lock"]


class NetworkRuntime(Protocol):
    """The parts of ``tephra.pipeline.Runtime`` the closure search reads."""

    @property
    def airports(self) -> AirportCatalogue: ...

    @property
    def policy(self) -> OperatorPolicy: ...

    @property
    def cones(self) -> Mapping[str, HazardCone]: ...

    @property
    def situations(self) -> Mapping[str, Situation]: ...


_LOCKS: "weakref.WeakKeyDictionary[object, asyncio.Lock]" = weakref.WeakKeyDictionary()


def run_lock(runtime: object) -> asyncio.Lock:
    """The runtime's one recovery-run lock."""
    return _LOCKS.setdefault(runtime, asyncio.Lock())


def network_icaos(schedule: Schedule) -> set[str]:
    return {f.origin for f in schedule.flights} | {f.dest for f in schedule.flights}


def network_closures(
    runtime: NetworkRuntime,
    schedule: Schedule,
    *,
    at: datetime,
    tafs: Mapping[str, Taf],
    metars: Mapping[str, Metar],
) -> list[Closure]:
    """Closures, now or within the planning horizon, of the airports the schedule flies to."""
    network = network_icaos(schedule)
    airports = [airport for airport in runtime.airports.all() if airport.icao in network]
    return find_closures(
        airports,
        cones=list(runtime.cones.values()),
        layers=[layer for s in runtime.situations.values() for layer in s.official_layers],
        tafs=tafs,
        metars=metars,
        at=at,
        horizon_end=at + timedelta(hours=MAX_HORIZON_H),
        policy=runtime.policy,
    )
