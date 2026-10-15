"""``GET /api/advisories/{id}/chain``: the four steps assembled from the store, nulls for
missing records, no dispatcher name or budget word, 404 for an unknown id.

Until the server mounts ``routes_chain`` the test mounts it itself.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tephra.api import routes_chain
from tephra.api.server import create_app
from tephra.config import PROJECT_ROOT, Settings
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    DisagreementReading,
    DutyBrief,
    DutyDispatch,
    DutyItem,
    DutyItemKind,
    DutyPriority,
    DutyRun,
    OperatorPolicy,
    PlannedAction,
    PlannerDecision,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    PolicySummary,
    RunMode,
    TickReport,
    ToolCallRecord,
)
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import proxy_flight_number

ADVISORY_ID = "adv_0123456789ab"
DECIDED_ID = "adv_fedcba987654"
PLANLESS_ID = "adv_00000000beef"
ASSESSMENT_ID = "PA-0123456789ab"
PLAN_ID = "PLAN-0123456789ab"
CONE_ID = "CONE-0123456789ab"
HEX = "8a0123"
FLIGHT_ID = f"{HEX}:263300"
ITEM_ID = "DI-0123456789ab"
DISPATCHER = "Ana K"
POLICY = load_policy(PROJECT_ROOT / "data")
# Copied from tests/test_ui_ai_quiet.py: the cause of a pause is said in the assistant's home only.
QUOTA_TEXT = re.compile(
    r"quota|used up|closed by google|free ai|next slot|\bspent\b|calls today|calls left"
    r"|share of calls|\bpacing\b|resets? (?:at|once)|reset was due|AI budget",
    re.I,
)


@dataclass
class FakeRuntime:
    """The parts of ``tephra.pipeline.Runtime`` the chain route and the lifespan touch."""

    settings: Settings
    store: Store
    bus: EventBus = field(default_factory=EventBus)
    mode: RunMode = RunMode.LIVE
    replay_run_since: None = None
    policy: OperatorPolicy = field(default_factory=lambda: POLICY)
    policy_summary: PolicySummary = field(default_factory=lambda: PolicySummary.of(POLICY))

    async def tick(self, *, reason: str = "scheduler") -> TickReport:
        at = timeutil.now()
        return TickReport(started_at=at, finished_at=at, mode=self.mode, reason=reason)

    async def aclose(self) -> None:
        await self.store.aclose()


def make_advisory(advisory_id: str = ADVISORY_ID, **changes: Any) -> Advisory:
    at = timeutil.now()
    fields: dict[str, Any] = {
        "id": advisory_id,
        "version": 1,
        "status": AdvisoryStatus.DRAFT,
        "created_at": at,
        "updated_at": at,
        "replay": False,
        "volcano_id": "263300",
        "volcano_name": "Semeru",
        "flight_id": FLIGHT_ID,
        "proxy_flight": proxy_flight_number(HEX),
        "callsign": "GIA417",
        "hex": HEX,
        "type_icao": "B738",
        "action": ActionKind.HOLD,
        "hold_fl": 350,
        "minutes_to_entry": 14,
        "inside_now": False,
        "fuel_line": "HOLD 20 MIN x 42 KG/MIN (NARROWBODY) = 840 KG",
        "plume_mode": PlumeMode.WIDENED,
        "confidence": 0.7,
        "cone_id": CONE_ID,
        "assessment_id": ASSESSMENT_ID,
        "plan_id": PLAN_ID,
        "header": "TEPHRA COMPANY ADVISORY - RING OF FIRE AIR (FICTIONAL) - NOT FOR OPERATIONAL"
        " USE",
        "body": "HOLD PRESENT POSITION FL350. ASH SFC/FL150 AHEAD, ENTRY 14 MIN. REPORT VAR.",
        "cost_note": "HOLD 20 MIN 840 KG",
        "sources": [],
        "input_hash": "0" * 64,
        "llm_backend": "stub",
        "model_id": "stub",
        "prompt_hashes": {"plume_reader": "a" * 64, "planner": "b" * 64, "drafter": "c" * 64},
        "dedupe_key": "DD-0123456789ab",
    }
    fields.update(changes)
    return Advisory(**fields)


def make_assessment() -> PlumeAssessment:
    return PlumeAssessment(
        id=ASSESSMENT_ID,
        volcano_id="263300",
        created_at=timeutil.now(),
        input_hash="0" * 64,
        estimate=PlumeEstimate(
            mode=PlumeMode.WIDENED,
            base_fl=0,
            top_fl=150,
            bearing_from_deg=200,
            bearing_to_deg=260,
            extent_km=120,
            horizon_h=6,
            confidence=0.7,
            sources_used=["VAA-DARWIN-1", "VONA-263300-1"],
            disagreements_explained=[
                DisagreementReading(
                    discrepancy_id="D-1234abcd",
                    reading="The advisory carries the higher top",
                    which_source_we_lean_on="VAA-DARWIN-1",
                    why="The notice says not observed, which never lowers a top",
                )
            ],
            uncertainty_notes="The satellite view is cloud-covered",
            rationale="The advisory's top and sector, widened for the wind spread",
        ),
        llm_backend="stub",
        model_id="stub",
        prompt_hash="a" * 64,
        outcome="STUB",
        attempts=0,
    )


def make_plan() -> PlannedAction:
    return PlannedAction(
        id=PLAN_ID,
        flight_id=FLIGHT_ID,
        cone_id=CONE_ID,
        decision=PlannerDecision(
            action=ActionKind.HOLD,
            hold_fl=350,
            reasoning="Hold clear of the band until the next advisory",
            alternatives_considered=[ActionKind.CHANGE_LEVEL],
        ),
        tool_calls=[
            ToolCallRecord(
                name="check_level_band", args={"fl": 350}, result_summary="FL350 is clear"
            )
        ],
        llm_backend="stub",
        model_id="stub",
        prompt_hash="b" * 64,
        outcome="STUB",
    )


def make_duty_run() -> DutyRun:
    at = timeutil.now() - timedelta(minutes=1)
    item = DutyItem(
        id=ITEM_ID,
        kind=DutyItemKind.PLAN,
        subject=FLIGHT_ID,
        label="Plan RFA4821 (Semeru): enters the area in 14 min",
        mandatory=True,
        urgency=1,
        volcano_id="263300",
    )
    other = DutyItem(
        id="DI-ffffffffffff",
        kind=DutyItemKind.ASSESS,
        subject="263300",
        label="Plume read: Semeru",
        mandatory=True,
        urgency=0,
        volcano_id="263300",
    )
    return DutyRun(
        id="DUTY-0123456789ab",
        started_at=at,
        finished_at=at,
        replay=False,
        trigger="tick",
        worklist=[other, item],
        dispatches=[
            DutyDispatch(tool="assess_volcanoes", item_ids=[other.id], ok=True, result="", ms=3),
            DutyDispatch(tool="plan_flights", item_ids=[item.id], ok=True, result="", ms=5),
        ],
        brief=DutyBrief(
            summary="One flight approaches the area.",
            priorities=[
                DutyPriority(item_id=other.id, why="The plume read comes first"),
                DutyPriority(item_id=item.id, why="Entry within the operator's hold limit"),
            ],
        ),
        outcome="STUB",
        llm_backend="stub",
        model_id="stub",
        prompt_hash="d" * 64,
        decided_at=at,
        recorded_wall_at=at,
    )


class Harness:
    def __init__(self) -> None:
        self.runtime: FakeRuntime | None = None

    async def factory(self, settings: Settings) -> Runtime:
        store = open_store(settings)
        for advisory in (
            make_advisory(),
            make_advisory(
                DECIDED_ID,
                status=AdvisoryStatus.APPROVED,
                decided_by=DISPATCHER,
                decided_at=timeutil.now(),
                validation_notes=["BODY MUST ASK THE CREW FOR A VOLCANIC ACTIVITY REPORT (VAR)"],
            ),
            make_advisory(PLANLESS_ID, plan_id="PLAN-000000000000"),
        ):
            created = await store.compare_and_set_advisory(
                advisory.id, 0, advisory.model_dump(mode="json")
            )
            assert created
        assessment = make_assessment()
        await store.put(Collection.ASSESSMENTS, assessment.id, assessment.model_dump(mode="json"))
        plan = make_plan()
        await store.put(Collection.PLANS, plan.id, plan.model_dump(mode="json"))
        run = make_duty_run()
        await store.put(Collection.DUTY, run.id, run.model_dump(mode="json"))
        self.runtime = FakeRuntime(settings=settings, store=store)
        return cast(Runtime, self.runtime)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin="zulu-4711",
        task_token="task-token-for-tests-0123456789abcdef",
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


def mount_chain(app: FastAPI) -> None:
    paths = {getattr(route, "path", None) for route in app.routes}
    if "/api/advisories/{advisory_id}/chain" not in paths:
        app.include_router(routes_chain.router, prefix="/api")


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, runtime_factory=Harness().factory)
    mount_chain(app)
    with TestClient(app) as test_client:
        yield test_client


def test_the_chain_assembles_the_four_steps_from_the_store(client: TestClient) -> None:
    response = client.get(f"/api/advisories/{ADVISORY_ID}/chain")
    assert response.status_code == 200, response.text
    chain = response.json()
    assert chain["advisory_id"] == ADVISORY_ID
    assert chain["flight"] == proxy_flight_number(HEX)
    assert chain["volcano_name"] == "Semeru"

    coordinator = chain["coordinator"]
    assert coordinator["run_id"] == "DUTY-0123456789ab"
    assert (coordinator["rank"], coordinator["of"]) == (2, 2)
    assert coordinator["why"] == "Entry within the operator's hold limit"
    assert coordinator["outcome"] == "STUB"
    assert coordinator["decided_at"].endswith("Z")

    plume = chain["plume"]
    assert plume["assessment_id"] == ASSESSMENT_ID
    assert (plume["mode"], plume["base_fl"], plume["top_fl"]) == ("WIDENED", 0, 150)
    assert plume["leaned_on"][0]["which_source_we_lean_on"] == "VAA-DARWIN-1"
    assert plume["checks"] == [
        "citations",
        "times",
        "numbers",
        "mode",
        "geometry",
        "hypothesis",
        "narrowing",
    ]
    assert plume["attempts"] == 0

    plan = chain["plan"]
    assert plan["plan_id"] == PLAN_ID
    assert plan["model_id"] == "stub"
    assert plan["repaired"] is False
    assert plan["tool_calls"] == [
        {"name": "check_level_band", "args": {"fl": 350}, "result_summary": "FL350 is clear"}
    ]
    assert plan["reasoning"] == "Hold clear of the band until the next advisory"
    assert plan["reasoning_checks"] == ["clock words"]
    assert (plan["action"], plan["target"]) == ("HOLD", "FL350")
    assert plan["checks"][0] == "allowed action"
    assert "hold level and time" in plan["checks"]

    draft = chain["draft"]
    assert draft["model_id"] == "stub"
    assert draft["outcome"] == "STUB"
    assert draft["repaired"] is False
    assert draft["numbers_in_body"] == 3  # 350, 150, 14
    assert draft["validation_notes"] == []
    assert draft["drafted_at"].endswith("Z")
    assert draft["checks"] == [
        "allowed action",
        "listed alternate",
        "listed reroute",
        "numbers from facts",
        "places from facts",
        "no clock times",
        "no CLOSED",
        "VAR line",
    ]


def test_a_chain_with_a_missing_plan_says_so_and_never_500s(client: TestClient) -> None:
    response = client.get(f"/api/advisories/{PLANLESS_ID}/chain")
    assert response.status_code == 200, response.text
    chain = response.json()
    assert chain["plan"] is None
    assert chain["plume"] is not None
    assert chain["draft"]["model_id"] == "stub"


def test_the_chain_carries_no_dispatcher_name_and_no_quota_word(client: TestClient) -> None:
    response = client.get(f"/api/advisories/{DECIDED_ID}/chain")
    assert response.status_code == 200, response.text
    text = response.text
    assert DISPATCHER not in text
    assert "decided_by" not in text
    assert not QUOTA_TEXT.search(text), QUOTA_TEXT.search(text)
    draft = response.json()["draft"]
    assert draft["repaired"] is True
    assert len(draft["validation_notes"]) == 1


@pytest.mark.parametrize("advisory_id", ["adv_ffffffffffff", "adv_not-an-id", "DUTY-0123456789ab"])
def test_an_unknown_advisory_is_404(client: TestClient, advisory_id: str) -> None:
    response = client.get(f"/api/advisories/{advisory_id}/chain")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
