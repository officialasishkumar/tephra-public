"""What the recovery agent can ask for, and the checks on what it answers.

``Toolbox`` holds one recovery run: the disruption, the scenarios the solver has produced and
every tool result so far. Code computes all of it; the agent (or the stub) only chooses which
scenarios to run and which one to recommend. ``validate_recommendation`` holds the written
rationale to the tool results: a number, time, flight, aircraft, scenario or airport that no
tool returned is rejected.
"""

import asyncio
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from pydantic import Field

from tephra.models import Airport, OperatorPolicy, TephraModel
from tephra.recovery.models import (
    Closure,
    RecoveryActionKind,
    RecoveryScenario,
    Schedule,
    SolveStatus,
)
from tephra.recovery.solver import describe_disruption, solve_recovery
from tephra.util.hashing import SHORT_HASH_LEN

__all__ = ["Recommendation", "Toolbox", "validate_recommendation"]

MAX_SCENARIOS: Final = 6
MAX_RATIONALE_CHARS: Final = 700
MAX_RISKS: Final = 3
MAX_RISK_CHARS: Final = 200
LISTED_FLIGHTS: Final = 25
"""Flights named in one tool result; the counts always cover all of them."""

_SCENARIO_ID = re.compile(rf"\bSC-[0-9a-f]{{{SHORT_HASH_LEN}}}\b")
_TAIL = re.compile(r"\bRFA-T\d{2}\b")
_FLIGHT = re.compile(r"\bRFA\d{3,4}(?:/\d{2}[A-Z]{3})?\b")
_CODE = re.compile(r"\b[A-Z]{3,4}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}Z?")
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_ENTITIES: Final = (_SCENARIO_ID, _TAIL, _FLIGHT)
_PLAIN_CAPS: Final = frozenset(
    {"USD", "UTC", "RFA", "FDP", "NOTAM", "TAF", "METAR", "SIGMET", "VAA"}
)
"""Capitalised abbreviations that are not airport codes."""


class Recommendation(TephraModel):
    scenario_id: str
    rationale: str
    risks: list[str] = Field(default_factory=list)


def _hhmmz(moment: datetime) -> str:
    return f"{moment:%H:%M}Z"


class Toolbox:
    def __init__(
        self,
        schedule: Schedule,
        closures: Sequence[Closure],
        *,
        now: datetime,
        policy: OperatorPolicy,
        airports: Mapping[str, Airport],
    ) -> None:
        self.schedule = schedule
        self.closures = list(closures)
        self.now = now
        self.policy = policy
        self.airports = airports
        self.scenarios: dict[str, RecoveryScenario] = {}
        self.evidence: list[str] = []
        self.accepted: Recommendation | None = None
        self.problems: list[str] = []

    # tools

    def disruption(self) -> dict[str, Any]:
        """Closures, what they block, and the choices the scenarios offer."""
        rules = self.policy.recovery
        found = describe_disruption(self.schedule, self.closures, now=self.now, policy=self.policy)
        result = {
            "now_utc": _hhmmz(self.now),
            "closures": [self._closure(closure) for closure in found.closures],
            "flights_blocked": len(found.blocked_flights),
            "passengers_blocked": found.blocked_pax,
            "blocked_flights": found.blocked_flights[:LISTED_FLIGHTS],
            "airborne_flights_landing_closed": found.airborne_at_risk,
            "flights_the_plan_may_change": found.free_flights,
            "flights_left_as_they_are": found.frozen_flights,
            "planning_horizon_until_utc": _hhmmz(found.horizon_end),
            "scenario_extensions_min": [
                0,
                rules.scenario_extend_1_min.value,
                rules.scenario_extend_2_min.value,
            ],
            "longest_delay_allowed_min": rules.max_delay_min.value,
        }
        return self._remember(result)

    async def run_scenario(
        self,
        extend_min: int,
        protect_flights: Sequence[str] | None = None,
        max_delay_min: int | None = None,
    ) -> dict[str, Any]:
        """Solve the day with every closure lasting ``extend_min`` minutes longer."""
        rules = self.policy.recovery
        known = {flight.key for flight in self.schedule.flights}
        protect = [code.strip().upper() for code in protect_flights or ()]
        problems = []
        if not 0 <= extend_min <= rules.scenario_extend_2_min.value:
            problems.append(f"extend_min must be from 0 to {rules.scenario_extend_2_min.value}")
        if unknown := sorted(set(protect) - known):
            problems.append(f"UNKNOWN FLIGHTS {', '.join(unknown)}")
        if max_delay_min is not None and not 0 < max_delay_min <= rules.max_delay_min.value:
            problems.append(f"max_delay_min must be from 1 to {rules.max_delay_min.value}")
        if problems:
            return {"error": "; ".join(problems)}
        if len(self.scenarios) >= MAX_SCENARIOS:
            return {
                "error": f"AT MOST {MAX_SCENARIOS} SCENARIOS PER RUN; COMPARE THE ONES YOU HAVE"
            }
        scenario = await asyncio.to_thread(
            solve_recovery,
            self.schedule,
            self.closures,
            now=self.now,
            policy=self.policy,
            airports=self.airports,
            extend_min=extend_min,
            protect_flights=protect,
            max_delay_min=max_delay_min,
        )
        self.scenarios[scenario.id] = scenario
        return self._remember(self._summary(scenario))

    def compare(self, scenario_ids: Sequence[str]) -> dict[str, Any]:
        """Totals of several scenarios side by side, with the cost difference to the first."""
        missing = [i for i in scenario_ids if i not in self.scenarios]
        if missing or not scenario_ids:
            return {"error": f"UNKNOWN SCENARIOS {', '.join(missing) or '(none given)'}"}
        chosen = [self.scenarios[i] for i in scenario_ids]
        first = next((s.totals.total_usd for s in chosen if s.totals is not None), 0)
        rows = [self._row(scenario, first) for scenario in chosen]
        solved = [s for s in chosen if s.totals is not None]
        result: dict[str, Any] = {"scenarios_compared": len(chosen), "scenarios": rows}
        if solved:
            result["lowest_cost_scenario_id"] = min(solved, key=_cost).id
        return self._remember(result)

    def submit(
        self, scenario_id: str, rationale: str, risks: Sequence[str] | None
    ) -> dict[str, Any]:
        recommendation = Recommendation(
            scenario_id=scenario_id.strip(), rationale=rationale.strip(), risks=list(risks or [])
        )
        self.problems = validate_recommendation(
            recommendation,
            scenarios=self.scenarios,
            evidence="\n".join(self.evidence),
            airports=self.airports,
        )
        if not self.problems:
            self.accepted = recommendation
        return {"accepted": not self.problems, "problems": self.problems}

    # tool results

    def _remember(self, result: dict[str, Any]) -> dict[str, Any]:
        self.evidence.append(json.dumps(result, ensure_ascii=True))
        return result

    def _closure(self, closure: Closure) -> dict[str, Any]:
        airport = self.airports.get(closure.icao)
        return {
            "airport_icao": closure.icao,
            "airport_iata": airport.iata if airport is not None else None,
            "closed_from_utc": _hhmmz(closure.start),
            "closed_until_utc": _hhmmz(closure.end),
            "end_is_published": not closure.open_ended,
            "reason": closure.reason,
            "source_ids": closure.source_ids,
        }

    def _summary(self, scenario: RecoveryScenario) -> dict[str, Any]:
        result: dict[str, Any] = {
            "scenario_id": scenario.id,
            "label": scenario.label,
            "closure_extension_min": scenario.extend_min,
            "status": scenario.status.value,
            "solver_status": scenario.solver_status,
            "closed_until_utc": {c.icao: _hhmmz(c.end) for c in scenario.closures},
        }
        if scenario.totals is None:
            return result
        cancelled = [a for a in scenario.actions if a.kind is RecoveryActionKind.CANCEL]
        swaps = [a for a in scenario.actions if a.kind is RecoveryActionKind.SWAP]
        result |= {
            "totals": scenario.totals.model_dump(),
            "cancelled_flights": [a.flight_key for a in cancelled][:LISTED_FLIGHTS],
            "swaps": [
                {"flight": a.flight_key, "from_tail": a.tail, "to_tail": a.new_tail}
                for a in swaps[:LISTED_FLIGHTS]
            ],
            "ferry_flights": [
                {
                    "tail": leg.tail,
                    "from": leg.origin,
                    "to": leg.dest,
                    "departs_utc": _hhmmz(leg.dep),
                }
                for leg in scenario.ferry_legs[:LISTED_FLIGHTS]
            ],
        }
        return result

    @staticmethod
    def _row(scenario: RecoveryScenario, first_usd: int) -> dict[str, Any]:
        row: dict[str, Any] = {
            "scenario_id": scenario.id,
            "label": scenario.label,
            "status": scenario.status.value,
        }
        if scenario.totals is not None:
            totals = scenario.totals
            row |= {
                "total_usd": totals.total_usd,
                "cancelled_flights": totals.cancelled_flights,
                "delayed_flights": totals.delayed_flights,
                "delay_min": totals.delay_min,
                "swapped_flights": totals.swapped_flights,
                "passengers_affected": totals.pax_affected,
                "usd_more_than_first": totals.total_usd - first_usd,
            }
        return row


def _cost(scenario: RecoveryScenario) -> int:
    return scenario.totals.total_usd if scenario.totals is not None else 0


# --- the checks ---------------------------------------------------------------------------------


def validate_recommendation(
    rec: Recommendation,
    *,
    scenarios: Mapping[str, RecoveryScenario],
    evidence: str,
    airports: Mapping[str, Airport],
) -> list[str]:
    problems: list[str] = []
    chosen = scenarios.get(rec.scenario_id)
    if chosen is None:
        problems.append(f"UNKNOWN SCENARIO {rec.scenario_id}: RUN IT FIRST AND USE ITS scenario_id")
    elif chosen.status is SolveStatus.NO_PLAN:
        problems.append(f"SCENARIO {rec.scenario_id} HAS NO PLAN ({chosen.solver_status})")
    if not 20 <= len(rec.rationale) <= MAX_RATIONALE_CHARS:
        problems.append(f"rationale must be 20 to {MAX_RATIONALE_CHARS} characters")
    if len(rec.risks) > MAX_RISKS or any(len(risk) > MAX_RISK_CHARS for risk in rec.risks):
        problems.append(f"at most {MAX_RISKS} risks of {MAX_RISK_CHARS} characters each")
    texts = [("rationale", rec.rationale), *((f"risk {i}", r) for i, r in enumerate(rec.risks, 1))]
    known = _airport_codes(airports)
    for field, text in texts:
        if not (text.isascii() and text.replace("\n", " ").isprintable()):
            problems.append(f"{field} must be plain printable ASCII")
            continue
        problems += [f"{field} {issue}" for issue in _invented(text, evidence, known)]
    return problems


def _airport_codes(airports: Mapping[str, Airport]) -> frozenset[str]:
    return frozenset({*airports, *(airport.iata for airport in airports.values() if airport.iata)})


def _invented(text: str, evidence: str, airport_codes: frozenset[str]) -> list[str]:
    """What ``text`` says that no tool result says."""
    issues: list[str] = []
    for pattern, noun in ((_SCENARIO_ID, "scenario"), (_FLIGHT, "flight"), (_TAIL, "aircraft")):
        if missing := sorted(set(pattern.findall(text)) - set(pattern.findall(evidence))):
            issues.append(f"NAMES {noun} {', '.join(missing)} THAT NO TOOL RETURNED")
    stripped = _strip(text)
    seen_codes = set(_CODE.findall(_strip(evidence)))
    codes = {c for c in _CODE.findall(stripped) if c in airport_codes or len(c) == 4}
    if missing := sorted(codes - seen_codes - _PLAIN_CAPS):
        issues.append(f"NAMES airports {', '.join(missing)} THAT NO TOOL RETURNED")
    if missing := sorted(_times(text) - _times(evidence)):
        issues.append(f"USES times {', '.join(missing)} THAT NO TOOL RETURNED")
    if missing := sorted(_numbers(text) - _numbers(evidence), key=float):
        issues.append(f"HAS NUMBERS NOT IN THE TOOL RESULTS: {', '.join(missing)}")
    return issues


def _strip(text: str) -> str:
    for pattern in _ENTITIES:
        text = pattern.sub(" ", text)
    return text


def _times(text: str) -> set[str]:
    return {token.rstrip("Z").lstrip("0") or "0" for token in _TIME.findall(text)}


def _numbers(text: str) -> set[str]:
    bare = _TIME.sub(" ", _strip(text))
    tokens = {raw.rstrip(",").replace(",", "") for raw in _NUMBER.findall(bare)}
    return {_plain(float(token)) for token in tokens if token}


def _plain(value: float) -> str:
    return str(int(value)) if value.is_integer() else repr(value)
