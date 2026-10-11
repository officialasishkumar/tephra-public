"""Backtest: the metrics on shapes with known answers, lead time, a real replay case run
offline (arm D), the arm G call cap, and the report writer with its number check.

No network and no live model: the case plays through ``ReplaySource`` on a fixed clock, and the
report model is a scripted backend.
"""

import importlib.util
import json
import math
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel
from shapely.geometry import Point, box

from tephra.agents.llm import LlmCall, LlmPart, StubBackend, Tier
from tephra.backtest.metrics import (
    EARTH_RADIUS_KM,
    Footprint,
    Projection,
    footprint_lead,
    lead_minutes,
    score_tick,
    summarise,
    summarise_leads,
)
from tephra.backtest.models import BacktestScorecard, CaseScore
from tephra.backtest.report import (
    ReportProse,
    ReportUnavailable,
    build_report,
    render_digest,
    validate_prose,
)
from tephra.backtest.runner import (
    _CappedGemini,
    load_scorecard,
    run_backtest,
    run_case,
    store_scorecard,
    tick_times,
    write_scorecard,
)
from tephra.config import PROJECT_ROOT, Settings
from tephra.models import GeoPolygon
from tephra.replay.cases import case_path, load_case
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore

DATA_DIR = PROJECT_ROOT / "data"
CASE = "java-live-20261010"
AT = datetime(2026, 10, 10, 6, 0, tzinfo=UTC)

needs_case = pytest.mark.skipif(
    not (case_path(DATA_DIR, CASE) / "manifest.json").is_file(),
    reason=f"the {CASE} replay case is not in this checkout",
)


def settings(tmp_path: Path, **changes: Any) -> Settings:
    return Settings(_env_file=None, llm="stub", cache_dir=tmp_path / "cache", **changes)


# --- metrics ----------------------------------------------------------------------------


@pytest.mark.parametrize("lat", [0.0, 45.0, -8.0])
def test_the_projection_keeps_area(lat: float) -> None:
    lon0 = 110.0
    projection = Projection(lat, lon0)
    polygon = GeoPolygon(
        coordinates=[
            [(lon0, lat), (lon0 + 2, lat), (lon0 + 2, lat + 2), (lon0, lat + 2), (lon0, lat)]
        ]
    )
    shape = projection.shape(polygon)

    expected = (
        EARTH_RADIUS_KM**2
        * math.radians(2)
        * (math.sin(math.radians(lat + 2)) - math.sin(math.radians(lat)))
    )
    assert shape.area == pytest.approx(expected, rel=2e-3)
    assert projection.point(lat, lon0) == pytest.approx((0.0, 0.0), abs=1e-9)


def test_the_projection_unwraps_longitudes_across_the_antimeridian() -> None:
    projection = Projection(0.0, 179.5)
    polygon = GeoPolygon(
        coordinates=[[(179.0, 0), (-179.0, 0), (-179.0, 1), (179.0, 1), (179.0, 0)]]
    )

    assert projection.shape(polygon).area == pytest.approx(2 * 111.19**2, rel=5e-3)


def tick(
    zone: Any, official: Any, truth: Any, *, zone_top: int = 300, tops: Sequence[int] = (250,)
):
    footprints = [
        Footprint("f", "v", AT, AT, truth, top_ft=top * 100) for top in tops if not truth.is_empty
    ]
    return score_tick(
        t=AT,
        volcano_id="v",
        cone_mode="WIDENED",
        zone=zone,
        official=official,
        truth=truth,
        footprints=footprints,
        zone_top_ft=zone_top * 100,
        airports={"AAAA": Point(1, 1), "BBBB": Point(9, 9)},
        floor_ok=True,
        input_leaks=0,
    )


def test_a_wider_zone_covers_more_and_pays_for_it() -> None:
    official = box(0, 0, 2, 2)  # 4
    zone = box(0, 0, 3, 2)  # 6, holds the official area
    truth = box(1, 0, 4, 2)  # 6: 4 of it inside the zone, 2 inside the official area

    score = tick(zone, official, truth)

    assert score.coverage == pytest.approx(4 / 6)
    assert score.coverage_official == pytest.approx(2 / 6)
    assert score.coverage_gain == pytest.approx(2 / 6)
    assert score.overwarn == pytest.approx(2 / 6)  # 2 of the zone's 6 is not in the truth
    assert score.excess_vs_official == pytest.approx(1.5)
    assert score.bias == pytest.approx(1.0)
    assert score.csi == pytest.approx(4 / 8)
    assert score.csi_official == pytest.approx(2 / 8)
    assert score.centroid_km == pytest.approx(1.0)
    assert score.hausdorff_km == pytest.approx(1.0)
    assert score.vertical_hit is True
    assert (score.airports_in_truth, score.airports_covered) == (["AAAA"], ["AAAA"])


def test_a_zone_below_the_footprint_top_misses_vertically() -> None:
    zone = box(0, 0, 2, 2)

    assert tick(zone, zone, zone, zone_top=200, tops=(250, 150)).vertical_hit is False
    assert tick(zone, zone, zone, zone_top=250, tops=(250, 150)).vertical_hit is True


def test_ratios_without_a_denominator_are_none_not_zero() -> None:
    zone = box(0, 0, 2, 2)

    score = tick(zone, zone, box(0, 0, 0, 0))  # nothing issued later

    assert score.truth_area_km2 == 0
    for name in (
        "coverage",
        "coverage_official",
        "coverage_gain",
        "overwarn",
        "bias",
        "hausdorff_km",
        "centroid_km",
        "vertical_hit",
    ):
        assert getattr(score, name) is None, name
    assert score.excess_vs_official == pytest.approx(1.0)
    assert summarise([score]).coverage_mean is None


def minutes(*values: int) -> list[datetime]:
    return [AT - timedelta(minutes=value) for value in values]


def test_lead_runs_back_through_the_unbroken_covered_ticks() -> None:
    issued = AT
    ticks = list(zip(minutes(150, 120, 90, 60, 30), (False, True, False, True, True), strict=True))

    assert lead_minutes(issued, ticks) == 60  # the 90-minute tick was not covered
    assert lead_minutes(issued, [*ticks, (AT - timedelta(minutes=5), False)]) is None
    assert lead_minutes(issued, []) is None


def test_lead_is_capped_at_a_day() -> None:
    ticks = [(AT - timedelta(hours=h), True) for h in (30, 26, 23, 12)]

    assert lead_minutes(AT, ticks) == 23 * 60


def test_incremental_lead_is_the_zone_lead_minus_the_official_lead() -> None:
    footprint = Footprint("f", "v", AT, AT, box(0, 0, 1, 1), None)
    zone = list(zip(minutes(180, 150, 120, 90, 60, 30), [True] * 6, strict=True))
    official = list(zip(minutes(180, 150, 120, 90, 60, 30), [False] * 3 + [True] * 3, strict=True))
    late = footprint_lead(footprint, zone, official)
    missed = footprint_lead(footprint, [(AT - timedelta(minutes=30), False)], zone)
    never = footprint_lead(footprint, zone, [(AT - timedelta(minutes=30), False)])

    assert (late.lead_zone_min, late.lead_official_min, late.incremental_min) == (180, 90, 90)
    assert (never.lead_official_min, never.incremental_min) == (None, 180)
    assert missed.incremental_min is None
    summary = summarise_leads(0.9, [late, missed, never])
    assert (summary.n_footprints, summary.n_missed, summary.n_covered_before_official) == (3, 1, 2)
    assert (summary.median_min, summary.p90_min) == (135.0, pytest.approx(171.0))


# --- a real replay case, offline ---------------------------------------------------------


@needs_case
def test_ticks_start_at_the_window_and_stop_inside_it() -> None:
    case = load_case(DATA_DIR, CASE)

    times = tick_times(case, timedelta(minutes=30))

    assert times[0] == case.recorded_from
    assert times[-1] <= case.recorded_to < times[-1] + timedelta(minutes=30)
    assert {b - a for a, b in pairwise(times)} == {timedelta(minutes=30)}


@needs_case
async def test_arm_d_replays_a_case_without_a_model_and_keeps_its_floor(tmp_path: Path) -> None:
    first = await run_case(CASE, settings=settings(tmp_path))
    second = await run_case(CASE, settings=settings(tmp_path))

    assert first == second  # deterministic
    assert (first.arm, first.models.backend, first.models.calls) == ("D", "stub", 0)
    assert first.floor_violations == 0
    assert first.input_leaks == 0
    assert first.ticks
    assert all(t.floor_ok and t.cone_mode == "OFFICIAL" for t in first.ticks)
    assert {t.t for t in first.ticks} <= set(
        tick_times(load_case(DATA_DIR, CASE), timedelta(minutes=30))
    )
    assert first.latest_input_ts is not None
    assert first.latest_input_ts <= first.t_last + timedelta(minutes=5)
    scored = [t for t in first.ticks if t.coverage is not None]
    assert scored
    # The stub never widens the official area: the gain is nil and the excess is one.
    assert all(abs(t.coverage_gain or 0) < 1e-3 for t in scored)
    assert all(t.excess_vs_official == pytest.approx(1.0, abs=1e-3) for t in scored)
    for lead in first.lead:
        assert lead.n_covered_before_official == 0
        assert lead.median_min in (None, 0.0)


@needs_case
async def test_the_scorecard_round_trips_and_goes_to_the_store(tmp_path: Path) -> None:
    scorecard = await run_backtest([CASE], settings=settings(tmp_path))
    path = tmp_path / "out" / "scorecard.json"

    write_scorecard(scorecard, path)

    assert load_scorecard(path) == scorecard
    assert list(scorecard.overall) == ["D"]
    store = SqliteStore(tmp_path / "s.sqlite3", tmp_path / "blobs")
    await store_scorecard(store, scorecard)
    stored = await store.get(Collection.BACKTEST, "latest")
    assert stored is not None
    assert BacktestScorecard.model_validate(stored) == scorecard


@needs_case
async def test_a_case_the_model_arm_cannot_run_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="arm G needs TEPHRA_LLM=gemini"):
        await run_case(CASE, settings=settings(tmp_path), arm="G")


def test_arm_g_stops_at_its_call_cap(tmp_path: Path) -> None:
    gemini = Settings(_env_file=None, llm="gemini", GEMINI_API_KEY="test-key", cache_dir=tmp_path)
    llm = _CappedGemini(gemini, max_calls=2)

    assert [llm.reserve("main") for _ in range(4)] == [True, True, False, False]
    assert llm.calls == 2
    assert _CappedGemini(gemini, max_calls=0).reserve("main") is False


# --- the report --------------------------------------------------------------------------


@pytest.fixture
async def scorecard(tmp_path: Path) -> BacktestScorecard:
    if not (case_path(DATA_DIR, CASE) / "manifest.json").is_file():
        pytest.skip(f"the {CASE} replay case is not in this checkout")
    return await run_backtest([CASE], settings=settings(tmp_path))


class ScriptedReportLlm:
    """A model backend that answers with the next scripted text (or no answer)."""

    name = "gemini"

    def __init__(self, answers: list[str | None]) -> None:
        self.answers = answers
        self.prompts: list[str] = []

    def model_id(self, tier: Tier) -> str:
        return "scripted-lite"

    async def pace(self, tier: str) -> None:
        return None

    def reserve(self, tier: Tier) -> bool:
        return True

    def exhaust(self, tier: Tier) -> None:
        raise AssertionError("not used")

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        assert tier == "lite"
        self.prompts.append("\n".join(part.text or "" for part in parts))
        text = self.answers.pop(0)
        call = LlmCall(backend="gemini", model_id="scripted-lite", prompt_hash="x", raw_text=text)
        if text is None:
            return None, call.model_copy(update={"error": "timeout"})
        return schema.model_validate_json(text), call


def prose_for(card: BacktestScorecard, **changes: Any) -> str:
    prose = {
        "summary": f"Cases run: {len(card.cases)}.",
        "cases": [
            {"case_id": c.case_id, "arm": c.arm, "text": "The zone matched the official area."}
            for c in card.cases
        ],
        "limits": "The later official area has its own lag.",
    } | changes
    return json.dumps(prose)


async def test_the_stub_report_uses_only_scorecard_figures_and_says_no_model(
    scorecard: BacktestScorecard,
) -> None:
    text = await build_report(scorecard, StubBackend())

    assert "NO MODEL" in text
    assert "Decision support only" in text
    assert f"| {CASE} | D |" in text
    assert all(caveat in text for caveat in scorecard.caveats)


async def test_an_accepted_answer_is_rendered_with_the_code_table(
    scorecard: BacktestScorecard,
) -> None:
    llm = ScriptedReportLlm([prose_for(scorecard)])

    text = await build_report(scorecard, llm)

    assert "prose written by scripted-lite" in text
    assert "The zone matched the official area." in text
    assert render_digest(scorecard) in llm.prompts[0]


async def test_a_number_that_is_not_in_the_scorecard_is_repaired_once(
    scorecard: BacktestScorecard,
) -> None:
    bad = prose_for(scorecard, summary="The zone covered 77.7% of everything.")
    llm = ScriptedReportLlm([bad, prose_for(scorecard)])

    text = await build_report(scorecard, llm)

    assert "77.7" not in text
    assert "HAS NUMBERS NOT IN THE INPUT: 77.7" in llm.prompts[1]


async def test_two_bad_answers_leave_no_report(scorecard: BacktestScorecard) -> None:
    bad = prose_for(scorecard, limits="It was issued at 1030Z.")
    llm = ScriptedReportLlm([bad, bad])

    with pytest.raises(ReportUnavailable, match=r"^AI UNAVAILABLE: the report failed its checks"):
        await build_report(scorecard, llm)


async def test_a_model_failure_is_reported_and_nothing_is_substituted(
    scorecard: BacktestScorecard,
) -> None:
    with pytest.raises(ReportUnavailable, match=r"^AI UNAVAILABLE: timeout"):
        await build_report(scorecard, ScriptedReportLlm([None]))


def test_the_checks_name_unknown_cases_and_missing_notes(scorecard: BacktestScorecard) -> None:
    prose = ReportProse.model_validate_json(prose_for(scorecard, cases=[]))

    assert validate_prose(prose, scorecard) == [
        "CASES MUST HAVE ONE NOTE PER CASE RUN, IN THE INPUT ORDER, WITH ITS ARM"
    ]


# --- the script --------------------------------------------------------------------------


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location(
        "backtest_script", PROJECT_ROOT / "scripts" / "backtest.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_case
def test_the_script_writes_the_scorecard_and_refuses_a_report_without_gemini(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TEPHRA_LLM", "stub")
    monkeypatch.setenv("TEPHRA_CACHE_DIR", str(tmp_path / "cache"))
    out = tmp_path / "out"
    stale = out / "REPORT.md"
    out.mkdir()
    stale.write_text("old", encoding="utf-8")

    code = load_script().main(["--case", CASE, "--out", str(out), "--report"])

    printed = capsys.readouterr().out
    assert code == 1
    assert "AI UNAVAILABLE: the report needs TEPHRA_LLM=gemini" in printed
    scorecard = load_scorecard(out / "scorecard.json")
    assert [c.case_id for c in scorecard.cases] == [CASE]
    assert isinstance(scorecard.cases[0], CaseScore)


def test_the_script_rejects_an_unknown_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("TEPHRA_LLM", "stub")

    with pytest.raises(SystemExit, match="unknown replay case"):
        load_script().main(["--case", "nowhere", "--out", str(tmp_path)])


# --- the route ---------------------------------------------------------------------------


def route_client(runtime_store: SqliteStore) -> TestClient:
    from fastapi import FastAPI

    from tephra.api import ApiError
    from tephra.api.routes_backtest import router
    from tephra.api.server import _json

    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.runtime = SimpleNamespace(store=runtime_store)

    @app.exception_handler(ApiError)
    async def api_error(_: Any, exc: ApiError) -> Any:
        return _json(exc.body(), exc.status_code)

    return TestClient(app)


async def test_the_route_serves_the_stored_scorecard_else_the_file_else_404(
    scorecard: BacktestScorecard, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tephra.api import routes_backtest

    store = SqliteStore(tmp_path / "r.sqlite3", tmp_path / "blobs")
    client = route_client(store)
    monkeypatch.setattr(routes_backtest, "SCORECARD_PATH", tmp_path / "scorecard.json")

    missing = client.get("/api/backtest")
    assert (missing.status_code, missing.json()["error"]) == (404, "not_found")

    write_scorecard(scorecard, tmp_path / "scorecard.json")
    from_file = client.get("/api/backtest")
    assert BacktestScorecard.model_validate(from_file.json()) == scorecard

    stored = scorecard.model_copy(update={"step_min": 60})
    await store_scorecard(store, stored)
    assert client.get("/api/backtest").json()["step_min"] == 60

    (tmp_path / "scorecard.json").write_text("{", encoding="utf-8")
    await store.delete(Collection.BACKTEST, "latest")
    assert client.get("/api/backtest").status_code == 503
