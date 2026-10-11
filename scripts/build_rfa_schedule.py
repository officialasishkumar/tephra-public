"""Build the synthetic schedule of the fictional airline Ring of Fire Air (RFA).

One operating day, 30 A320-family aircraft based at CGK, SUB, DPS, UPG and KNO, flying
out-and-back excursions on real Indonesian domestic airport pairs from ``data/airports.json``
(chosen by hand, then checked against the real routes in ``data/routes_apac.json`` when that
file is present). Everything else is
invented: tail numbers, times, loads and crews. The seed is fixed, so a re-run rewrites the
same files.

    uv run python scripts/build_rfa_schedule.py
"""

from __future__ import annotations

import argparse
import json
import random
from itertools import pairwise
from pathlib import Path

from tephra.config import PROJECT_ROOT
from tephra.geo.units import distance_nm
from tephra.models import Airport, AirportFile
from tephra.recovery.models import RfaCrew, RfaFlight, RfaTail, ScheduleHeader
from tephra.recovery.schedule import SCHEDULE_DIR, block_minutes

SEED = 20260907
HEADER = ScheduleHeader(
    label=(
        "Ring of Fire Air (RFA) is a fictional airline. This schedule is synthetic: only the"
        " airport pairs are real."
    ),
    seed=SEED,
    anchor_utc_offset_h=7,
    cruise_kt=430,
    overhead_min=30,
    generated_by="scripts/build_rfa_schedule.py",
)

FLEET: dict[str, tuple[int, ...]] = {
    "WIII": (11, 3),
    "WARR": (5, 1),
    "WADD": (5, 1),
    "WAAA": (2, 0),
    "WIMM": (2, 0),
}
"""Home base -> (A320 count, A321 count)."""
SEATS = {"A320": 180, "A321": 220}
SPOKES: dict[str, tuple[str, ...]] = {
    "WIII": (
        "WARR",
        "WADD",
        "WAHI",
        "WAHS",
        "WAHQ",
        "WARA",
        "WIMM",
        "WIPP",
        "WIDD",
        "WAAA",
        "WADL",
        "WAMM",
    ),
    "WARR": ("WIII", "WADD", "WIHH", "WAAA", "WADL", "WAMM"),
    "WADD": ("WIII", "WARR", "WIHH", "WADL", "WAAA", "WAMM"),
    "WAAA": ("WIII", "WARR", "WADD", "WAMM"),
    "WIMM": ("WIII", "WIDD", "WIPP"),
}
BANKS_MIN = (300, 345, 390, 450, 510, 570)
"""Departure banks (minutes after 00:00 local): the first leg of each aircraft leaves in one."""
BANK_JITTER_STEPS = 3
DUTY_BUDGET_MIN = 720
"""An aircraft's day is planned to end this long after its crew reports."""
REPORT_BEFORE_MIN = 60
TURN_RANGE_MIN = (40, 55)
LOAD_FACTOR_RANGE = (0.72, 0.97)
FLIGHT_COUNT_RANGE = (120, 150)


def build(airports: dict[str, Airport]) -> tuple[list[RfaTail], list[RfaCrew], list[RfaFlight]]:
    rng = random.Random(SEED)
    tails: list[RfaTail] = []
    crews: list[RfaCrew] = []
    drafts: list[dict[str, object]] = []
    for base, (a320, a321) in FLEET.items():
        for kind in ["A320"] * a320 + ["A321"] * a321:
            number = len(tails) + 1
            tail = RfaTail(
                tail=f"RFA-T{number:02d}",
                type=kind,
                seats=SEATS[kind],
                home_base=base,
                crew_id=f"RFA-C{number:02d}",
            )
            legs = _rotation(rng, airports, tail)
            tails.append(tail)
            crews.append(
                RfaCrew(
                    crew_id=tail.crew_id,
                    base=base,
                    report_min=int(legs[0]["std_min"]) - REPORT_BEFORE_MIN,
                )
            )
            drafts.extend(legs)
    drafts.sort(key=lambda leg: (leg["std_min"], leg["origin"], leg["tail"]))
    flights = [
        RfaFlight(flight_no=f"RFA{101 + index}", **leg)  # type: ignore[arg-type]
        for index, leg in enumerate(drafts)
    ]
    return tails, crews, flights


def _rotation(
    rng: random.Random, airports: dict[str, Airport], tail: RfaTail
) -> list[dict[str, object]]:
    """Out-and-back excursions from the aircraft's base until its duty budget is spent."""
    clock = rng.choice(BANKS_MIN) + 5 * rng.randrange(BANK_JITTER_STEPS)
    report = clock - REPORT_BEFORE_MIN
    legs: list[dict[str, object]] = []
    pair = 0
    while True:
        # Of two random spokes the nearer one flies: most real domestic flying is short-haul.
        spoke = min(
            (rng.choice(SPOKES[tail.home_base]) for _ in range(2)),
            key=lambda dest: _block(airports, tail.home_base, dest),
        )
        block = _block(airports, tail.home_base, spoke)
        turn = 5 * rng.randrange(TURN_RANGE_MIN[0] // 5, TURN_RANGE_MIN[1] // 5 + 1)
        back = clock + block + turn
        if back + block - report > DUTY_BUDGET_MIN:
            break
        pair += 1
        pair_id = f"{tail.tail[-3:]}-P{pair}"
        for origin, dest, std in ((tail.home_base, spoke, clock), (spoke, tail.home_base, back)):
            legs.append(
                {
                    "origin": origin,
                    "dest": dest,
                    "std_min": std,
                    "block_min": block,
                    "tail": tail.tail,
                    "pax_booked": round(tail.seats * rng.uniform(*LOAD_FACTOR_RANGE)),
                    "pair_id": pair_id,
                }
            )
        clock = back + block + 5 * rng.randrange(TURN_RANGE_MIN[0] // 5, TURN_RANGE_MIN[1] // 5 + 1)
    if not legs:
        raise SystemExit(f"{tail.tail} has no flights: lower DUTY_BUDGET_MIN or the bank times")
    return legs


def _block(airports: dict[str, Airport], origin: str, dest: str) -> int:
    a, b = airports[origin], airports[dest]
    return block_minutes(distance_nm(a.lat, a.lon, b.lat, b.lon), HEADER)


def _lines(items: list[dict[str, object]]) -> str:
    body = ",\n".join("  " + json.dumps(item, separators=(", ", ": ")) for item in items)
    return f"[\n{body}\n]"


def write(
    out_dir: Path, tails: list[RfaTail], crews: list[RfaCrew], flights: list[RfaFlight]
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "fleet.json": ("tails", [tail.model_dump(mode="json") for tail in tails], None),
        "crews.json": ("crews", [crew.model_dump(mode="json") for crew in crews], None),
        "flights.json": (
            "flights",
            [flight.model_dump(mode="json", exclude_none=True) for flight in flights],
            HEADER.model_dump(mode="json"),
        ),
    }
    for name, (key, items, header) in files.items():
        head = "" if header is None else f'  "header": {json.dumps(header)},\n'
        text = f'{{\n{head}  "{key}": {_lines(items)}\n}}\n'
        (out_dir / name).write_text(text, encoding="utf-8")


def check_routes(path: Path) -> None:
    """Every excursion pair must be a real route (either direction) in the VRS-derived file."""
    if not path.is_file():
        return
    chains = json.loads(path.read_text(encoding="utf-8"))["routes"].values()
    real = {frozenset(hop) for chain in chains for hop in pairwise(chain.split("-"))}
    unknown = sorted(
        f"{base}-{spoke}"
        for base, spokes in SPOKES.items()
        for spoke in spokes
        if frozenset((base, spoke)) not in real
    )
    if unknown:
        raise SystemExit(f"not in {path.name}: {', '.join(unknown)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    args = parser.parse_args()
    catalogue = AirportFile.model_validate_json((args.data_dir / "airports.json").read_bytes())
    airports = {airport.icao: airport for airport in catalogue.airports}
    check_routes(args.data_dir / "routes_apac.json")
    tails, crews, flights = build(airports)
    low, high = FLIGHT_COUNT_RANGE
    if not low <= len(flights) <= high:
        raise SystemExit(f"{len(flights)} flights: outside {low} to {high}; change the seed inputs")
    write(args.data_dir / SCHEDULE_DIR, tails, crews, flights)
    print(f"wrote {len(tails)} tails, {len(crews)} crews, {len(flights)} flights")


if __name__ == "__main__":
    main()
