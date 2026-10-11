"""What an SRA draft is made from: the region's picture, flights, advisories and VAR drafts.

Everything here is read from the runtime or the store; nothing is computed that the pipeline
has not already decided. A flight's advisory is the newest one for it in the current mode.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from tephra.desk import approvals, failures
from tephra.models import (
    Advisory,
    AiFailure,
    AviationColor,
    ExposedFlight,
    HazardCone,
    Region,
    RunMode,
    Situation,
    SystemState,
    Vona,
)
from tephra.regdocs.models import DocKind, VarDraft
from tephra.regdocs.registry import list_docs
from tephra.regdocs.runtime import DocsRuntime
from tephra.util import timeutil

__all__ = [
    "Evidence",
    "FlightView",
    "NoActiveVolcano",
    "UnknownRegion",
    "VolcanoView",
    "gather_evidence",
]

LOOKUP_LIMIT = 200


class UnknownRegion(Exception): ...


class NoActiveVolcano(Exception):
    """No volcano of the region is in the current picture, so there is nothing to assess."""


@dataclass(frozen=True)
class VolcanoView:
    situation: Situation
    cone: HazardCone | None
    color: AviationColor
    vona: Vona | None


@dataclass(frozen=True)
class FlightView:
    flight: ExposedFlight
    advisory: Advisory | None
    failure: AiFailure | None


@dataclass(frozen=True)
class Evidence:
    created: datetime
    replay: bool
    state: SystemState
    region: Region
    volcanoes: list[VolcanoView]
    flights: list[FlightView]
    aircraft_types: list[tuple[str, int]]
    advisories: list[Advisory]
    var_drafts: list[VarDraft]


async def gather_evidence(runtime: DocsRuntime, region_key: str) -> Evidence:
    region = next((item for item in runtime.settings.regions if item.key == region_key), None)
    if region is None:
        raise UnknownRegion(region_key)
    volcanoes = [
        _volcano_view(runtime, situation)
        for _, situation in sorted(runtime.situations.items())
        if region.bbox.contains(situation.volcano.lat, situation.volcano.lon)
    ]
    if not volcanoes:
        raise NoActiveVolcano(region_key)
    ids = {view.situation.volcano.id for view in volcanoes}
    replay = runtime.mode is RunMode.REPLAY
    state = await runtime.system_state()
    advisories = [
        advisory
        for advisory in await approvals.list_advisories(runtime.store, limit=LOOKUP_LIMIT)
        if advisory.volcano_id in ids and advisory.replay == replay
    ]
    open_failures = {
        failure.flight_id: failure
        for failure in await failures.list_failures(
            runtime.store, open_only=True, replay=replay, limit=LOOKUP_LIMIT
        )
    }
    newest: dict[str, Advisory] = {}
    for advisory in advisories:  # newest first
        newest.setdefault(advisory.flight_id, advisory)
    exposed = sorted(
        (flight for flight in runtime.exposed.values() if flight.volcano_id in ids),
        key=lambda flight: (not flight.inside_now, flight.minutes_to_entry, flight.id),
    )
    drafts = [
        doc
        for doc in await list_docs(runtime.store, kind=DocKind.VAR, limit=LOOKUP_LIMIT)
        if isinstance(doc, VarDraft) and doc.volcano_id in ids and doc.replay == replay
    ]
    return Evidence(
        created=timeutil.now(),
        replay=replay,
        state=state,
        region=region,
        volcanoes=volcanoes,
        flights=[
            FlightView(flight, newest.get(flight.id), open_failures.get(flight.id))
            for flight in exposed
        ],
        aircraft_types=_aircraft_types(runtime, region),
        advisories=advisories,
        var_drafts=drafts,
    )


def _volcano_view(runtime: DocsRuntime, situation: Situation) -> VolcanoView:
    vona = max(situation.vonas, key=lambda item: item.issued_at, default=None)
    return VolcanoView(
        situation=situation,
        cone=runtime.cones.get(situation.volcano.id),
        color=vona.color_code if vona is not None else AviationColor.UNKNOWN,
        vona=vona,
    )


def _aircraft_types(runtime: DocsRuntime, region: Region) -> list[tuple[str, int]]:
    counts = Counter(
        aircraft.type_icao or "unknown"
        for aircraft in runtime.aircraft()
        if aircraft.airline and region.bbox.contains(aircraft.lat, aircraft.lon)
    )
    return sorted(counts.items())
