"""The workspace's dry run: a push file checked record by record exactly as a push would be,
against the current time, with nothing taken in."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from test_airline_api import AT, airline_settings, open_client, runtime_of, signup
from test_connect import connection, position
from test_pipeline import FixtureSource, make_runtime, make_settings

from tephra.desk import connections
from tephra.models import AIRLINE_FORMAT, POSITIONS_FORMAT
from tephra.util import timeutil
from tephra.util.timeutil import FixedClock, use_clock

PLAN = {"flight": "RFA101", "callsign": "RFA101", "origin_icao": "WIII", "dest_icao": "WARR"}
MIXED: dict[str, Any] = {
    "format": AIRLINE_FORMAT,
    "positions": [
        position(),
        position(hex="zz0000"),
        position(observed_at=timeutil.to_iso(AT - timedelta(hours=2))),
        position(hex="8a0a1f", callsign="PKABC"),
    ],
    "flight_plans": [PLAN, {**PLAN, "dest_icao": "WIII"}],
    "pilot_reports": [{"callsign": "RFA101"}],
}


async def test_the_dry_run_refuses_what_a_push_refuses_in_the_same_words(
    tmp_path: Path,
) -> None:
    with use_clock(FixedClock(AT)):
        result = connections.dry_run(MIXED, AT)
        runtime = make_runtime(make_settings(tmp_path), FixtureSource())
        try:
            pushed = await runtime.take_push(
                connection(),
                MIXED["positions"],
                plans=MIXED["flight_plans"],
                reports=MIXED["pilot_reports"],
            )
        finally:
            await runtime.aclose()

    said = [(p.section, p.index, p.reason) for p in result.rejected]
    by_push = [
        (p.section, p.index, p.reason.replace("TEPHRA's clock", "the current time"))
        for p in pushed.rejected
    ]
    assert said == by_push
    assert [(p.section, p.index) for p in result.rejected] == [
        ("positions", 1),
        ("positions", 2),
        ("flight_plans", 1),
        ("pilot_reports", 0),
    ]
    assert "not within 5 min of the current time" in result.rejected[1].reason
    assert (result.positions.total, result.positions.accepted) == (4, 2)
    assert (result.flight_plans.total, result.flight_plans.accepted) == (2, 1)
    assert (result.pilot_reports.total, result.pilot_reports.accepted) == (1, 0)
    assert [(r.section, r.index, r.text, r.note) for r in result.accepted] == [
        ("positions", 0, "8a0a1e · BTK6711 · -5.26, 105.79 · FL144", None),
        ("positions", 3, "8a0a1f · PKABC · -5.26, 105.79 · FL144", connections.NOT_CHECKED_NOTE),
        ("flight_plans", 0, "RFA101 · WIII → WARR", None),
    ]
    assert result.checked_at == AT
    assert result.format == AIRLINE_FORMAT


def test_a_well_formed_pilot_report_is_checked_for_shape_only() -> None:
    report = {
        "callsign": "RFA101",
        "cues": ["SULPHUR_SMELL"],
        "observed_at": "2026-10-09T19:31:00Z",
    }
    result = connections.dry_run({"format": AIRLINE_FORMAT, "pilot_reports": [report]}, AT)
    assert [(r.text, r.note) for r in result.accepted] == [("RFA101 · 19:31Z", None)]


@pytest.mark.parametrize(
    "raw",
    [
        {"positions": [position()]},
        {"format": AIRLINE_FORMAT},
        {"format": "tephra.other/1", "positions": [position()]},
        {"format": POSITIONS_FORMAT, "flight_plans": [PLAN]},
        {"format": AIRLINE_FORMAT, "pilot_reports": [{}] * 21},
    ],
)
def test_a_file_that_is_not_a_push_says_why(raw: dict[str, Any]) -> None:
    with pytest.raises(connections.NotAPush) as caught:
        connections.dry_run(raw, AT)
    assert str(caught.value)


def test_the_route_is_private_capped_and_takes_nothing_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = {"format": POSITIONS_FORMAT, "positions": [position(observed_at=timeutil.to_iso(AT))]}
    with use_clock(FixedClock(AT)), open_client(airline_settings(tmp_path), monkeypatch)() as c:
        signed_out = c.post("/api/airline/feeds/dry-run", json=body)
        assert signup(c).status_code == 201
        before = dict(runtime_of(c).pushed)
        first = c.post("/api/airline/feeds/dry-run", json=body)
        not_a_push = c.post("/api/airline/feeds/dry-run", json={"format": AIRLINE_FORMAT})
        too_big = c.post(
            "/api/airline/feeds/dry-run",
            json={**body, "pad": "x" * (512 * 1024)},
        )
        runs = [c.post("/api/airline/feeds/dry-run", json=body) for _ in range(29)]  # 3rd-31st
        after = dict(runtime_of(c).pushed)

    assert signed_out.status_code == 401
    assert first.status_code == 200
    # Measured against the wall clock, which is not this test's replay clock: refused, kept.
    assert [p["section"] for p in first.json()["rejected"]] == ["positions"]
    assert "of the current time" in first.json()["rejected"][0]["reason"]
    assert (not_a_push.status_code, not_a_push.json()["error"]) == (422, "not_a_push")
    assert too_big.status_code == 413
    assert [r.status_code for r in runs] == [200] * 28 + [429]
    assert "Retry-After" in runs[-1].headers
    assert before == after == {}


def test_a_refusal_names_every_problem_in_plain_words() -> None:
    bad = {"hex": "zz", "lat": -5.2, "lon": 105.8}
    result = connections.dry_run({"format": AIRLINE_FORMAT, "positions": [bad]}, AT)
    [problem] = result.rejected

    assert problem.reason == (
        "hex: 6 characters, 0-9 and a-f; alt_baro_ft: needed; observed_at: needed"
    )
    assert "pattern" not in problem.reason
    many = {"hex": "zz", "lat": "x", "lon": 500, "alt_baro_ft": 1.5, "observed_at": "y"}
    [crowded] = connections.dry_run({"format": AIRLINE_FORMAT, "positions": [many]}, AT).rejected
    assert crowded.reason.endswith("; +2 more")
