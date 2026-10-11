"""Ask TEPHRA: the tools, the answer validator, the ADK run, voice and the HTTP routes.

No network and no key: a scripted ``BaseLlm`` registered for ``tephra-ask-scripted-*`` stands
in for Gemini, so the real ``LlmAgent``, ``FunctionTool`` wrapping and ``InMemoryRunner`` run.
"""

import json
import wave
from collections.abc import AsyncGenerator, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import pytest
from fastapi.testclient import TestClient
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.models.registry import LLMRegistry
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from tephra.agents import ask, voice
from tephra.agents.ask import (
    AiUnavailable,
    AskAnswer,
    AskClaim,
    AskEvidence,
    AskFailure,
    AskReply,
    AskToolkit,
    answer_question,
    store_ask,
    validate_reply,
)
from tephra.agents.llm import LlmCall, LlmPart, StubBackend, Tier
from tephra.api import routes_ask
from tephra.api.server import create_app
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk import audit
from tephra.feeds.airports import AirportCatalogue
from tephra.feeds.registry import LiveData
from tephra.geo.cone import geometry_to_shape
from tephra.geo.exposure import find_exposed
from tephra.models import (
    ActionKind,
    AdsbQueryPoint,
    AdsbSnapshot,
    Advisory,
    AdvisoryStatus,
    AiFailure,
    Aircraft,
    Airport,
    AuditAction,
    Discrepancy,
    DiscrepancyKind,
    DutyBrief,
    DutyDispatch,
    DutyItem,
    DutyItemKind,
    DutyPriority,
    DutyRun,
    FeedHealth,
    FeedId,
    FeedStatus,
    GeoPolygon,
    HazardCone,
    LlmBackendName,
    OfficialLayer,
    PlumeAssessment,
    PlumeEstimate,
    PlumeMode,
    Provenance,
    RerouteKind,
    RerouteOption,
    RerouteStatus,
    RunMode,
    Sigmet,
    Situation,
    SseEvent,
    TraceEvent,
    VaacCentre,
    Volcano,
)
from tephra.policy import load_policy
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util.events import EventBus
from tephra.util.hashing import proxy_flight_number
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 19, 0, tzinfo=UTC)
POLICY = load_policy(PROJECT_ROOT / "data")
SCRIPTED_MODEL = "tephra-ask-scripted-lite"
PIN = "zulu-4711"
ADVISORY_ID = "adv_0123456789ab"
CONE_ID = "CONE-0123456789ab"
SIGMET_ID = "SIGMET:WAAF:12:20261009T1820Z"

VOLCANO = Volcano(
    id="263300",
    name="Semeru",
    aliases=["SEMERU"],
    magma_code="SMR",
    country="Indonesia",
    lat=-8.108,
    lon=112.922,
    summit_elev_m=3676,
    observatory="PVMBG",
    vaac=VaacCentre.DARWIN,
)
BOX = GeoPolygon(
    coordinates=[[(113.0, -9.0), (114.0, -9.0), (114.0, -8.0), (113.0, -8.0), (113.0, -9.0)]]
)

Turn = list[types.Part] | Exception
_SCRIPT: list[Turn] = []
_REQUESTS: list[LlmRequest] = []


class ScriptedLlm(BaseLlm):
    """Answers each model turn with the next scripted parts, or raises a scripted error."""

    patterns: ClassVar[list[str]] = [r"tephra-ask-scripted-.*"]

    @classmethod
    def supported_models(cls) -> list[str]:
        return cls.patterns

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        _REQUESTS.append(llm_request)
        turn = _SCRIPT.pop(0) if _SCRIPT else [types.Part(text="DONE")]
        if isinstance(turn, Exception):
            raise turn
        yield LlmResponse(content=types.Content(role="model", parts=turn))


LLMRegistry.register(ScriptedLlm)


@pytest.fixture(autouse=True)
def script() -> Iterator[list[Turn]]:
    _SCRIPT.clear()
    _REQUESTS.clear()
    yield _SCRIPT
    _SCRIPT.clear()


def call(name: str, **args: Any) -> list[types.Part]:
    return [types.Part(function_call=types.FunctionCall(name=name, args=args))]


def reply_json(**fields: Any) -> list[types.Part]:
    body = {
        "answer": "",
        "claims": [],
        "status": "answered",
        "refusal_reason": None,
        "follow_ups": [],
        "language": "en",
        **fields,
    }
    return [types.Part(text=json.dumps(body))]


def claim(text: str, *evidence_ids: str, kind: str = "fact") -> dict[str, Any]:
    return {"text": text, "evidence_ids": list(evidence_ids), "kind": kind}


# --- the model backends -----------------------------------------------------------------


class GeminiStandIn:
    """What the Ask agent reads of a non-stub backend: its name, ids and budget."""

    def __init__(self, *, budget_left: bool = True) -> None:
        self.name: LlmBackendName = "gemini"
        self.reserved: list[str] = []
        self.exhausted: list[str] = []
        self._budget_left = budget_left
        self.heard: list[Any] = []
        self.parts: list[Sequence[LlmPart]] = []

    def model_id(self, tier: str) -> str:
        return SCRIPTED_MODEL

    async def pace(self, tier: str) -> None:
        return None

    def reserve(self, tier: str) -> bool:
        self.reserved.append(tier)
        return self._budget_left

    def exhaust(self, tier: str) -> None:
        self.exhausted.append(tier)
        self._budget_left = False

    async def structured(
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[BaseModel],
        stub: Callable[[], Any],
        temperature: float | None = None,
    ) -> tuple[Any, LlmCall]:
        self.parts.append(parts)
        value = self.heard.pop(0) if self.heard else None
        error = None if value is not None else "api_error 503 UNAVAILABLE"
        call_record = LlmCall(
            backend="gemini", model_id=SCRIPTED_MODEL, prompt_hash="0" * 64, error=error
        )
        return (None if value is None else schema.model_validate(value)), call_record


# --- the scene --------------------------------------------------------------------------


def make_aircraft(hex_id: str, callsign: str, *, lat: float, alt_ft: int) -> Aircraft:
    return Aircraft(
        hex=hex_id,
        callsign=callsign,
        type_icao="B738",
        lat=lat,
        lon=112.0,
        alt_baro_ft=alt_ft,
        gs_kt=480.0,
        track_deg=90.0,
        observed_at=AT,
        source_id="ADSB:-8.200:113.600:20261009T190000Z",
    )


EXPOSED_HEX, HIGH_HEX, SOUTH_HEX = "8a01f2", "8a0222", "8a0333"
EXPOSED_PROXY = proxy_flight_number(EXPOSED_HEX)
HIGH_PROXY = proxy_flight_number(HIGH_HEX)
SOUTH_PROXY = proxy_flight_number(SOUTH_HEX)


def make_cone() -> HazardCone:
    return HazardCone(
        id=CONE_ID,
        volcano_id=VOLCANO.id,
        assessment_id="PA-0123456789ab",
        mode=PlumeMode.OFFICIAL,
        confidence=0.7,
        llm_backend="stub",
        created_at=AT,
        horizon_h=6.0,
        valid_to=AT + timedelta(hours=6),
        geometry=BOX,
        base_ft=0,
        top_ft=15_000,
        official_source_ids=[SIGMET_ID],
    )


def make_situation() -> Situation:
    provenance = Provenance(
        source_id=SIGMET_ID,
        feed=FeedId.SIGMET,
        url="https://example.invalid/sigmet",
        fetched_at=AT,
        sha256="0" * 64,
    )
    sigmet = Sigmet(
        provenance=provenance,
        fir_id="WAAF",
        series_id="12",
        volcano_name="SEMERU",
        observed=True,
        base_ft=0,
        top_ft=15_000,
        polygon=BOX,
        valid_from=AT - timedelta(minutes=40),
        valid_to=AT + timedelta(hours=5),
        raw_text="WAAF SIGMET 12 VA CLD OBS SFC/FL150",
    )
    layer = OfficialLayer(
        source_id=SIGMET_ID,
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WAAF 12",
        volcano_id=VOLCANO.id,
        polygon=BOX,
        base_ft=0,
        top_ft=15_000,
        valid_from=AT - timedelta(minutes=40),
        valid_to=AT + timedelta(hours=5),
    )
    discrepancy = Discrepancy(
        id="D-0123abcd",
        volcano_id=VOLCANO.id,
        kind=DiscrepancyKind.HEIGHT_MISMATCH,
        aspect="top",
        source_ids=[SIGMET_ID, "VONA:SMR:20261009T1800Z"],
        values={SIGMET_ID: "FL150", "VONA:SMR:20261009T1800Z": "FL250"},
        summary="SIGMET tops the ash at FL150 and the VONA at FL250",
    )
    return Situation(
        volcano=VOLCANO,
        as_of=AT,
        mode=RunMode.LIVE,
        active_reasons=["VA SIGMET valid"],
        sigmets=[sigmet],
        official_layers=[layer],
        discrepancies=[discrepancy],
    )


def make_assessment() -> PlumeAssessment:
    estimate = PlumeEstimate(
        mode=PlumeMode.OFFICIAL,
        base_fl=0,
        top_fl=150,
        bearing_from_deg=80.0,
        bearing_to_deg=100.0,
        extent_km=30.0,
        horizon_h=6.0,
        confidence=0.7,
        sources_used=[SIGMET_ID],
        disagreements_explained=[],
        uncertainty_notes="Thin ash is hard to see.",
        rationale="The official SIGMET binds.",
    )
    return PlumeAssessment(
        id="PA-0123456789ab",
        volcano_id=VOLCANO.id,
        created_at=AT,
        input_hash="h" * 8,
        estimate=estimate,
        llm_backend="stub",
        model_id="stub",
        prompt_hash="p" * 8,
        outcome="STUB",
        attempts=0,
    )


def make_live() -> LiveData:
    snapshot = AdsbSnapshot(
        provenance=Provenance(
            source_id="ADSB:-8.200:113.600:20261009T190000Z",
            feed=FeedId.ADSB,
            url="https://example.invalid/adsb",
            fetched_at=AT,
            sha256="1" * 64,
        ),
        query=AdsbQueryPoint(lat=-8.2, lon=113.6, radius_nm=250),
        aircraft=[
            make_aircraft(EXPOSED_HEX, "GIA417", lat=-8.5, alt_ft=12_000),
            make_aircraft(HIGH_HEX, "JAL725", lat=-8.5, alt_ft=35_000),
            make_aircraft(SOUTH_HEX, "QFA43A", lat=-9.5, alt_ft=12_000),
        ],
    )
    live = LiveData()
    live.adsb = [snapshot]
    live.health = {
        FeedId.SIGMET: FeedHealth(
            feed=FeedId.SIGMET,
            status=FeedStatus.OK,
            cadence_s=60,
            last_success_at=AT - timedelta(seconds=30),
            record_count=4,
        )
    }
    return live


@dataclass
class FakeRuntime:
    """The parts of ``tephra.pipeline.Runtime`` Ask reads, plus what the routes publish to."""

    settings: Settings
    store: Store
    llm: Any
    live: LiveData = field(default_factory=make_live)
    mode: RunMode = RunMode.LIVE
    policy: Any = field(default_factory=lambda: POLICY)
    bus: EventBus = field(default_factory=EventBus)
    airports: AirportCatalogue = field(
        default_factory=lambda: AirportCatalogue(
            [
                Airport(icao="WARR", name="Juanda", country="ID", lat=-7.4, lon=112.8, elev_ft=9),
                Airport(
                    icao="WIII", name="Soekarno", country="ID", lat=-6.1, lon=106.7, elev_ft=26
                ),
            ],
            min_runway_m=1800,
        )
    )
    situations: dict[str, Situation] = field(default_factory=dict)
    assessments: dict[str, PlumeAssessment] = field(default_factory=dict)
    cones: dict[str, HazardCone] = field(default_factory=dict)
    exposed: dict[str, Any] = field(default_factory=dict)
    duty: Any = None
    published: list[tuple[str, Any]] = field(default_factory=list)
    traces: list[str] = field(default_factory=list)

    def trace(self, stage: Any, actor: Any, message: str, **_: Any) -> None:
        self.traces.append(message)

    async def aclose(self) -> None:
        await self.store.aclose()


def make_runtime(tmp_path: Path, llm: Any | None = None) -> FakeRuntime:
    settings = Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
        model_lite=SCRIPTED_MODEL,
    )
    runtime = FakeRuntime(
        settings=settings, store=open_store(settings), llm=llm if llm is not None else StubBackend()
    )
    cone = make_cone()
    runtime.situations[VOLCANO.id] = make_situation()
    runtime.assessments[VOLCANO.id] = make_assessment()
    runtime.cones[VOLCANO.id] = cone
    with use_clock(FixedClock(AT)):
        found = find_exposed(
            cone,
            list(runtime.live.adsb[0].aircraft),
            AT,
            lookahead_min=settings.exposure_lookahead_min,
            vertical_margin_ft=POLICY.exposure.vertical_margin_ft.value,
            hold_minutes=POLICY.fuel.hold_min.value,
        )
    runtime.exposed = {flight.id: flight for flight in found}
    return runtime


@pytest.fixture
async def runtime(tmp_path: Path) -> AsyncGenerator[FakeRuntime, None]:
    built = make_runtime(tmp_path)
    with use_clock(FixedClock(AT)):
        yield built
    await built.store.aclose()


def make_advisory() -> Advisory:
    return Advisory(
        id=ADVISORY_ID,
        version=1,
        status=AdvisoryStatus.DRAFT,
        created_at=AT,
        updated_at=AT,
        replay=False,
        volcano_id=VOLCANO.id,
        volcano_name="Semeru",
        flight_id=f"{EXPOSED_HEX}:{VOLCANO.id}",
        proxy_flight=EXPOSED_PROXY,
        callsign="GIA417",
        hex=EXPOSED_HEX,
        type_icao="B738",
        action=ActionKind.HOLD,
        hold_fl=350,
        minutes_to_entry=8,
        inside_now=False,
        fuel_line="HOLD 20 MIN x 42 KG/MIN (NARROWBODY) = 840 KG",
        plume_mode=PlumeMode.OFFICIAL,
        confidence=0.7,
        cone_id=CONE_ID,
        assessment_id="PA-0123456789ab",
        plan_id="PLAN-0123456789ab",
        header="TEPHRA COMPANY ADVISORY",
        body="HOLD PRESENT POSITION FL350.",
        cost_note="HOLD 20 MIN 840 KG",
        sources=[],
        input_hash="0" * 64,
        llm_backend="stub",
        model_id="stub",
        prompt_hashes={"plume_reader": "a" * 64, "planner": "b" * 64, "drafter": "c" * 64},
        dedupe_key="DD-0123456789ab",
    )


def make_reroute() -> RerouteOption:
    return RerouteOption(
        id="RR-0123456789ab",
        flight_id=f"{EXPOSED_HEX}:{VOLCANO.id}",
        cone_id=CONE_ID,
        kind=RerouteKind.REJOIN_TRACK,
        status=RerouteStatus.OK,
        note="Clear of the cone by the policy buffer",
        side="LEFT",
        fl=120,
        extra_nm=42.0,
        extra_min=6.0,
        route_string="DCT 0830S11130E DCT 0830S11400E",
    )


async def put_advisory_and_plan(runtime: FakeRuntime) -> None:
    flight_id = f"{EXPOSED_HEX}:{VOLCANO.id}"
    created = await runtime.store.compare_and_set_advisory(
        ADVISORY_ID, 0, make_advisory().model_dump(mode="json")
    )
    assert created
    plan = {
        "id": "PLAN-0123456789ab",
        "flight_id": flight_id,
        "cone_id": CONE_ID,
        "decision": {
            "action": "HOLD",
            "hold_fl": 350,
            "reasoning": "Hold clear of the band.",
            "alternatives_considered": [],
        },
        "fuel": {"formula": "HOLD 20 MIN = 840 KG"},
        "outcome": "ACCEPTED",
        "validation_errors": [],
    }
    await runtime.store.put(Collection.PLANS, "PLAN-0123456789ab", plan)
    await runtime.store.put(
        Collection.REROUTES, "RR-0123456789ab", make_reroute().model_dump(mode="json")
    )


# --- tools ------------------------------------------------------------------------------


async def test_tools_return_evidence_with_source_ids(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)

    listed = await kit.exposed_flights()
    assert listed["evidence_id"] == "T01"
    assert listed["count"] == 1
    assert listed["flights"][0]["proxy_flight"] == EXPOSED_PROXY
    assert listed["flights"][0]["level_fl"] == 120
    assert listed["flights"][0]["minutes_to_entry"] == 8
    assert "ADSB:-8.200:113.600:20261009T190000Z" in listed["source_ids"]

    cone = await kit.cone("semeru")
    assert cone["evidence_id"] == "T02"
    assert (cone["band"], cone["confidence_pct"]) == ("SFC/FL150", 70)
    assert SIGMET_ID in cone["source_ids"]

    situation = await kit.situation(VOLCANO.id)
    assert situation["official_layers"][0]["band"] == "SFC/FL150"
    assert situation["plume_reading"]["top_fl"] == 150
    assert (await kit.discrepancies("SEMERU"))["discrepancies"][0]["kind"] == "HEIGHT_MISMATCH"

    feeds = await kit.feeds()
    assert feeds["feeds"][0]["feed"] == "sigmet"
    assert feeds["source_ids"] == ["FEED:sigmet"]
    assert [item.id for item in kit.evidence] == ["T01", "T02", "T03", "T04", "T05"]
    assert [record.name for record in kit.records] == [
        "exposed_flights",
        "cone",
        "situation",
        "discrepancies",
        "feeds",
    ]


async def test_flight_is_found_by_id_proxy_number_or_callsign(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)
    by_callsign = await kit.flight("gia417")
    by_proxy = await kit.flight(EXPOSED_PROXY)
    by_id = await kit.flight(f"{EXPOSED_HEX}:{VOLCANO.id}")
    assert by_callsign["proxy_flight"] == by_proxy["proxy_flight"] == by_id["proxy_flight"]
    assert by_callsign["hold_cost"].startswith("HOLD")


async def test_a_failed_lookup_has_no_evidence_but_counts_as_a_call(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)
    missing = await kit.flight("NOPE123")
    assert "evidence_id" not in missing
    assert "NO EXPOSED FLIGHT" in missing["error"]
    unknown = await kit.cone("Krakatau")
    assert "ACTIVE: 263300 Semeru" in unknown["error"]
    assert kit.evidence == []
    assert len(kit.records) == 2
    assert kit.records[0].result_summary.startswith("ERROR")


async def test_the_seventh_tool_call_is_refused(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)
    for _ in range(ask.MAX_TOOL_CALLS):
        assert "evidence_id" in await kit.feeds()
    refused = await kit.feeds()
    assert "TOOL CALL LIMIT 6" in refused["error"]
    assert len(kit.evidence) == len(kit.records) == ask.MAX_TOOL_CALLS


async def test_advisory_plan_and_reroutes_come_from_the_store(runtime: FakeRuntime) -> None:
    await put_advisory_and_plan(runtime)
    kit = AskToolkit(runtime)

    by_id = await kit.advisory(advisory_id=ADVISORY_ID)
    by_flight = await kit.advisory(flight_id="GIA417")
    assert by_id["advisory_id"] == by_flight["advisory_id"] == ADVISORY_ID
    assert by_id["status"] == "DRAFT"
    assert by_id["hold_fl"] == 350
    assert "evidence_id" not in await kit.advisory()

    plan = await kit.plan(EXPOSED_PROXY)
    assert plan["ai_written_decision"]["action"] == "HOLD"
    assert plan["reroute_options"][0]["route_string"].startswith("DCT 0830S")
    options = await kit.reroute_options("GIA417")
    assert options["options"][0]["status"] == "OK"
    assert options["source_ids"] == ["RR-0123456789ab"]
    assert "NO PLAN" in (await kit.plan("JAL725"))["error"]


async def test_ai_failures_lists_the_open_ones(runtime: FakeRuntime) -> None:
    failure = AiFailure(
        id="AIF-0123456789ab",
        created_at=AT,
        replay=False,
        stage="planner",
        reason="PLANNER AGENT ERROR: RuntimeError",
        model_id="gemini-test",
        volcano_id=VOLCANO.id,
        volcano_name="Semeru",
        flight_id=f"{HIGH_HEX}:{VOLCANO.id}",
        proxy_flight=HIGH_PROXY,
        hex=HIGH_HEX,
        cone_id=CONE_ID,
        minutes_to_entry=9,
        inside_now=False,
    )
    await runtime.store.put(Collection.AI_FAILURES, failure.id, failure.model_dump(mode="json"))
    result = await AskToolkit(runtime).ai_failures()
    assert result["count"] == 1
    assert result["open_failures"][0]["proxy_flight"] == HIGH_PROXY


async def test_duty_brief_reads_the_duty_officers_latest_run(runtime: FakeRuntime) -> None:
    assert (await AskToolkit(runtime).duty_brief()) == {"error": "THE DUTY OFFICER HAS NOT RUN YET"}
    plan = DutyItem(
        id="DI-plan",
        kind=DutyItemKind.PLAN,
        subject=f"{HIGH_HEX}:{VOLCANO.id}",
        label=f"Plan {HIGH_PROXY} (Semeru): inside the area now",
        mandatory=True,
        urgency=0,
        volcano_id=VOLCANO.id,
    )
    runtime.duty = DutyRun(
        id="DUTY-0123456789ab",
        started_at=AT,
        finished_at=AT,
        replay=False,
        trigger="tick",
        worklist=[plan],
        dispatches=[
            DutyDispatch(
                tool="plan_flights", item_ids=["DI-plan"], ok=True, result="DRAFT HOLD", ms=900
            )
        ],
        brief=DutyBrief(
            summary="Semeru ash: one flight inside.",
            priorities=[DutyPriority(item_id="DI-plan", why="inside the area")],
            watch=["Semeru drift"],
        ),
        outcome="ACCEPTED",
        llm_backend="gemini",
        model_id="gemini-test-lite",
        prompt_hash="0" * 64,
    )
    toolkit = AskToolkit(runtime)
    result = await toolkit.duty_brief()
    assert result["summary"] == "Semeru ash: one flight inside."
    assert result["priorities"] == [
        {"work": f"Plan {HIGH_PROXY} (Semeru): inside the area now", "why": "inside the area"}
    ]
    assert result["delegated"][0]["tool"] == "plan_flights"
    assert result["left_undone_to_the_desk"] == []


async def test_what_if_band_lists_flights_that_become_exposed(runtime: FakeRuntime) -> None:
    before = dict(runtime.exposed)
    cone_before = runtime.cones[VOLCANO.id].model_copy()
    kit = AskToolkit(runtime)

    result = await kit.what_if_band(VOLCANO.id, 0, 350)

    assert result["exposed_now"] == 1
    assert result["exposed_in_what_if"] == 2
    assert [row["proxy_flight"] for row in result["become_exposed"]] == [HIGH_PROXY]
    assert result["stop_being_exposed_count"] == 0
    assert result["assumed"] == {"base_fl": 0, "top_fl": 350}
    assert result["real_band"] == "SFC/FL150"
    assert "NOT AN ADVISORY" in result["what_if_only"]
    assert runtime.exposed == before
    assert runtime.cones[VOLCANO.id] == cone_before


async def test_what_if_band_can_show_flights_that_stop_being_exposed(
    runtime: FakeRuntime,
) -> None:
    result = await AskToolkit(runtime).what_if_band(VOLCANO.id, 200, 300)
    assert [row["proxy_flight"] for row in result["stop_being_exposed"]] == [EXPOSED_PROXY]
    assert result["become_exposed_count"] == 0


async def test_what_if_extent_widens_the_cone_and_changes_nothing(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)
    result = await kit.what_if_extent(VOLCANO.id, 100.0)
    assert [row["proxy_flight"] for row in result["become_exposed"]] == [SOUTH_PROXY]
    assert result["assumed"] == {"extra_km": 100.0}
    assert (await kit.what_if_extent(VOLCANO.id, 5))["become_exposed_count"] == 0
    cone = runtime.cones[VOLCANO.id]
    assert cone.geometry == BOX
    assert set(runtime.exposed) == {f"{EXPOSED_HEX}:{VOLCANO.id}"}


def test_the_widened_area_covers_the_old_one_by_about_the_buffer() -> None:
    wide = ask._buffered(BOX, 100.0, ref_lon=VOLCANO.lon)
    old = geometry_to_shape(BOX, ref_lon=VOLCANO.lon)
    new = geometry_to_shape(wide, ref_lon=VOLCANO.lon)
    assert new.contains(old)
    # 100 km is about 0.9 degrees of latitude.
    assert old.bounds[1] - new.bounds[1] == pytest.approx(0.9, abs=0.02)


async def test_what_if_arguments_are_checked(runtime: FakeRuntime) -> None:
    kit = AskToolkit(runtime)
    assert "WHOLE LEVELS" in (await kit.what_if_band(VOLCANO.id, 350, 100))["error"]
    assert "WHOLE LEVELS" in (await kit.what_if_band(VOLCANO.id, 0, 350.5))["error"]  # type: ignore[arg-type]
    assert "WHOLE LEVELS" in (await kit.what_if_band(VOLCANO.id, 0, 700))["error"]
    assert "ABOVE 0" in (await kit.what_if_extent(VOLCANO.id, 0))["error"]
    assert "AT MOST" in (await kit.what_if_extent(VOLCANO.id, 5000))["error"]
    assert "NUMBER" in (await kit.what_if_extent(VOLCANO.id, "far"))["error"]  # type: ignore[arg-type]
    # A JSON number can arrive as 350.0.
    assert "evidence_id" in await AskToolkit(runtime).what_if_band(VOLCANO.id, 0.0, 350.0)  # type: ignore[arg-type]


# --- validator --------------------------------------------------------------------------


def evidence() -> list[AskEvidence]:
    return [
        AskEvidence(
            id="T01",
            tool="exposed_flights",
            args={},
            source_ids=[SIGMET_ID, CONE_ID],
            summary="exposed_flights()",
            result={
                "count": 1,
                "flights": [
                    {
                        "proxy_flight": "RFA4821",
                        "callsign": "GIA417",
                        "level_fl": 120,
                        "minutes_to_entry": 8,
                        "hazard_band": "SFC/FL150",
                        "alternate": "WARR",
                        "valid_to": "2026-10-09 23:50Z",
                    }
                ],
            },
        ),
        AskEvidence(
            id="T02", tool="feeds", args={}, source_ids=[], summary="feeds()", result={"count": 14}
        ),
    ]


def reply(answer: str, *claims: AskClaim, **fields: Any) -> AskReply:
    values: dict[str, Any] = {
        "answer": answer,
        "claims": list(claims),
        "status": "answered",
        "language": "en",
        **fields,
    }
    return AskReply.model_validate(values)


def problems_of(value: AskReply, question: str = "Which flights?") -> list[str]:
    return validate_reply(value, evidence(), question=question, airport_icaos={"WARR", "WIII"})


GOOD = reply(
    "RFA4821 (GIA417) enters the cone in 8 minutes at FL120; the band is SFC/FL150.",
    AskClaim(text="RFA4821 enters in 8 minutes", evidence_ids=["T01"], kind="number"),
    AskClaim(text="It flies FL120 under SFC/FL150", evidence_ids=["T01"], kind="fact"),
)


def test_a_grounded_answer_passes() -> None:
    assert problems_of(GOOD) == []


@pytest.mark.parametrize(
    ("answer", "needle"),
    [
        ("RFA4821 enters in 7 minutes.", "NUMBER 7"),
        ("RFA4821 flies FL130.", "NUMBER 130"),
        ("RFA9999 enters in 8 minutes.", "RFA9999"),
        ("Divert RFA4821 to WIII.", "WIII"),
        ("It reaches the cone at 23:51Z, in 8 minutes.", "TIME 23:51"),
        ("See CONE-ffffffffffff for 8 minutes.", "CONE-ffffffffffff"),
    ],
)
def test_an_invented_figure_is_rejected(answer: str, needle: str) -> None:
    claim_ok = AskClaim(text="RFA4821 enters in 8 minutes", evidence_ids=["T01"], kind="number")
    found = problems_of(reply(answer, claim_ok))
    assert any(needle in problem for problem in found), found


def test_figures_are_checked_in_claims_too() -> None:
    bad_claim = AskClaim(text="RFA4821 enters in 11 minutes", evidence_ids=["T01"], kind="number")
    assert any(
        "CLAIM 1" in p and "NUMBER 11" in p for p in problems_of(reply("RFA4821.", bad_claim))
    )


def test_a_claim_may_only_use_the_evidence_it_cites() -> None:
    # 14 is in T02 but the claim cites T01 only.
    claim_t01 = AskClaim(text="Fourteen feeds are listed", evidence_ids=["T01"], kind="number")
    assert any("NUMBER 14" in p for p in problems_of(reply("Feeds: 14.", claim_t01)))
    claim_t02 = AskClaim(text="Fourteen feeds are listed", evidence_ids=["T02"], kind="number")
    assert problems_of(reply("Feeds: 14.", claim_t02)) == []


def test_unknown_evidence_and_missing_claims_are_rejected() -> None:
    unknown = reply("RFA4821.", AskClaim(text="x", evidence_ids=["T09"], kind="fact"))
    assert any("UNKNOWN EVIDENCE T09" in p for p in problems_of(unknown))
    assert any("AT LEAST ONE CLAIM" in p for p in problems_of(reply("RFA4821.")))
    assert any("EMPTY" in p for p in problems_of(reply("  ", *GOOD.claims)))


def test_the_answer_length_is_limited() -> None:
    long_answer = reply("x" * (ask.MAX_ANSWER_CHARS + 1), *GOOD.claims)
    assert any("CHARACTERS" in p for p in problems_of(long_answer))


@pytest.mark.parametrize(
    "answer",
    ["RFA4821 is safe to fly.", "All clear for RFA4821 in 8 minutes.", "There is no risk."],
)
def test_an_answer_never_calls_anything_safe(answer: str) -> None:
    assert any("SAFE" in p for p in problems_of(reply(answer, *GOOD.claims)))


def test_a_refusal_has_a_reason_no_claims_and_only_the_questions_figures() -> None:
    refusal = reply(
        "I cannot say whether FL350 is safe; I can list the exposed flights.",
        status="refused",
        refusal_reason="Safety judgements are outside TEPHRA's products.",
    )
    assert problems_of(refusal, "Is FL350 safe?") == []
    assert any("NUMBER 350" in p for p in problems_of(refusal, "Is it safe?"))
    no_reason = reply("No.", status="refused")
    assert any("refusal_reason" in p for p in problems_of(no_reason))
    with_claims = reply(
        "No.", *GOOD.claims, status="refused", refusal_reason="Outside the products."
    )
    assert any("NO CLAIMS" in p for p in problems_of(with_claims))


def test_follow_ups_are_checked_against_all_evidence_and_the_question() -> None:
    fine = reply(GOOD.answer, *GOOD.claims, follow_ups=["What is the plan for RFA4821?"])
    assert problems_of(fine) == []
    invented = reply(GOOD.answer, *GOOD.claims, follow_ups=["What about FL410?"])
    assert any("A FOLLOW-UP" in p and "410" in p for p in problems_of(invented))
    assert problems_of(invented, "What about FL410?") == []


def test_a_decimal_or_comma_number_matches_its_evidence() -> None:
    corpus = [
        AskEvidence(
            id="T01",
            tool="cone",
            args={},
            source_ids=[],
            summary="cone()",
            result={"extent_km": 30.5, "feet": 15000},
        )
    ]
    answer = reply(
        "Extent 30.50 km and 15,000 ft.", AskClaim(text="x", evidence_ids=["T01"], kind="number")
    )
    assert validate_reply(answer, corpus, question="q", airport_icaos=[]) == []


# --- the ADK run ------------------------------------------------------------------------


async def ask_with(
    runtime: FakeRuntime, llm: GeminiStandIn, question: str = "Which flights enter the cone?"
) -> tuple[AskAnswer | AskFailure, list[TraceEvent]]:
    trace: list[TraceEvent] = []
    result = await answer_question(runtime, llm, question, trace=trace.append)
    return result, trace


GROUNDED = {
    "answer": f"{EXPOSED_PROXY} (GIA417) enters the cone in 8 minutes at FL120.",
    "claims": [claim(f"{EXPOSED_PROXY} enters in 8 minutes at FL120", "T01", kind="number")],
}


async def test_the_agent_calls_tools_and_answers(runtime: FakeRuntime, script: list[Turn]) -> None:
    script += [
        call("exposed_flights"),
        call("flight", flight_id="GIA417"),
        reply_json(**GROUNDED, follow_ups=["What plan was drafted for it?"]),
    ]
    llm = GeminiStandIn()
    result, trace = await ask_with(runtime, llm)

    assert isinstance(result, AskAnswer)
    assert result.status == "answered"
    assert result.llm_backend == "gemini"
    assert not result.repaired
    assert result.id.startswith("ask_")
    assert result.follow_ups == ["What plan was drafted for it?"]
    assert [item.id for item in result.evidence] == ["T01", "T02"]
    assert [record.name for record in result.tool_calls] == ["exposed_flights", "flight"]
    assert result.replay is False
    # One lite turn per model call: two tool turns and the answer.
    assert llm.reserved == ["lite"] * 3
    assert [e.message for e in trace if e.actor == "adk"][:2] == [
        "T01 exposed_flights()",
        "T02 flight(flight_id=GIA417)",
    ]
    assert all(event.stage.value == "ASK" for event in trace)
    # The question and the tools' content never reach the (public) trace.
    assert not any("cone?" in event.message or EXPOSED_PROXY in event.message for event in trace)


async def test_the_instruction_carries_the_prompt_and_the_schema(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [reply_json(**GROUNDED)]
    script[0:0] = [call("exposed_flights")]
    await ask_with(runtime, GeminiStandIn())
    request = _REQUESTS[0]
    instruction = str(request.config.system_instruction)
    assert "You answer questions from a dispatcher" in instruction
    assert '"evidence_ids"' in instruction
    declared = {d.name for tool in request.config.tools for d in tool.function_declarations}
    assert declared == {
        "situation",
        "discrepancies",
        "cone",
        "exposed_flights",
        "flight",
        "advisory",
        "plan",
        "reroute_options",
        "feeds",
        "ai_failures",
        "duty_brief",
        "what_if_band",
        "what_if_extent",
    }
    task = request.contents[0].parts[0].text
    assert "Active volcanoes: 263300 Semeru" in task
    assert "Mode: LIVE" in task


async def test_the_task_names_a_replay_and_the_open_flight(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    runtime.mode = RunMode.REPLAY
    script += [call("exposed_flights"), reply_json(**GROUNDED)]
    result = await answer_question(runtime, GeminiStandIn(), "q?", flight_id="8a01f2:263300")
    assert isinstance(result, AskAnswer)
    assert result.replay is True
    task = _REQUESTS[0].contents[0].parts[0].text
    assert "REPLAY" in task
    assert "8a01f2:263300" in task


async def test_a_rejected_answer_gets_one_repair_turn(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    wrong = {**GROUNDED, "answer": f"{EXPOSED_PROXY} enters the cone in 11 minutes at FL120."}
    script += [call("exposed_flights"), reply_json(**wrong), reply_json(**GROUNDED)]
    result, _ = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskAnswer)
    assert result.repaired
    repair = _REQUESTS[-1].contents[-1].parts[0].text
    assert "Code rejected the answer" in repair
    assert "NUMBER 11" in repair


async def test_two_rejected_answers_are_ai_unavailable(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    wrong = {**GROUNDED, "answer": f"{EXPOSED_PROXY} enters the cone in 11 minutes."}
    script += [call("exposed_flights"), reply_json(**wrong), reply_json(**wrong)]
    result, trace = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskFailure)
    assert result.reason.startswith("AI UNAVAILABLE: ")
    assert "NUMBER 11" in result.reason
    assert [item.id for item in result.evidence] == ["T01"]
    assert trace[-1].level == "error"
    assert "AI UNAVAILABLE" in trace[-1].message


async def test_text_that_is_not_json_is_unavailable_after_one_repair(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [[types.Part(text="The flight is fine.")], [types.Part(text="Still prose.")]]
    result, _ = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskFailure)
    assert "NOT VALID JSON" in result.reason


async def test_a_refusal_is_a_valid_answer(runtime: FakeRuntime, script: list[Turn]) -> None:
    script += [
        reply_json(
            answer="I cannot judge that; I can list what the products show.",
            status="refused",
            refusal_reason="Operational safety judgements are outside TEPHRA's products.",
        )
    ]
    result, _ = await ask_with(runtime, GeminiStandIn(), "Is it safe to fly?")
    assert isinstance(result, AskAnswer)
    assert result.status == "refused"
    assert result.claims == []


async def test_the_answer_follows_the_question_language(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [
        call("exposed_flights"),
        reply_json(
            answer=f"Penerbangan {EXPOSED_PROXY} masuk ke kerucut dalam 8 menit pada FL120.",
            claims=[claim(f"{EXPOSED_PROXY} masuk dalam 8 menit", "T01", kind="number")],
            language="id",
        ),
    ]
    result, _ = await ask_with(runtime, GeminiStandIn(), "Penerbangan mana yang terpengaruh?")
    assert isinstance(result, AskAnswer)
    assert result.language == "id"


async def test_a_seventh_tool_call_goes_back_to_the_model_as_an_error(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    feeds_answer = {
        "answer": "The sigmet feed is OK and holds 4 records.",
        "claims": [claim("The sigmet feed holds 4 records", "T01", kind="number")],
    }
    script += [call("feeds")] * 7 + [reply_json(**feeds_answer)]
    result, _ = await ask_with(runtime, GeminiStandIn())
    function_responses = [
        part.function_response.response
        for request in _REQUESTS[-1:]
        for content in request.contents
        for part in content.parts or []
        if part.function_response is not None
    ]
    assert "TOOL CALL LIMIT 6" in function_responses[-1]["error"]
    # Seven calls but only six have evidence, so the answer's claim to T01 stands.
    assert isinstance(result, AskAnswer)
    assert len(result.evidence) == 6
    assert len(result.tool_calls) == 6


async def test_a_looping_model_is_stopped_by_the_turn_limit(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [call("feeds")] * (ask.MAX_MODEL_TURNS + 2)
    result, _ = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskFailure)
    assert f"MODEL TURN LIMIT {ask.MAX_MODEL_TURNS} REACHED" in result.reason


async def test_an_exhausted_budget_stops_before_any_model_call(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [call("exposed_flights")]
    result, _ = await ask_with(runtime, GeminiStandIn(budget_left=False))
    assert _REQUESTS == []
    assert isinstance(result, AskFailure)
    assert "budget_exhausted" in result.reason
    assert result.evidence == []


async def test_a_spent_daily_quota_closes_the_lite_tier(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    from google.adk.models.google_llm import _ResourceExhaustedError

    quota = {
        "error": {
            "code": 429,
            "status": "RESOURCE_EXHAUSTED",
            "message": "quota",
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                }
            ],
        }
    }
    script += [_ResourceExhaustedError(genai_errors.ClientError(429, quota))]
    llm = GeminiStandIn()
    result, _ = await ask_with(runtime, llm)
    assert isinstance(result, AskFailure)
    assert "DAILY QUOTA SPENT" in result.reason
    assert llm.exhausted == ["lite"]


async def test_an_agent_error_is_unavailable_and_keeps_the_evidence(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [call("exposed_flights"), ValueError("boom")]
    result, _ = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskFailure)
    assert result.reason == "AI UNAVAILABLE: ASK AGENT ERROR: ValueError"
    assert [item.id for item in result.evidence] == ["T01"]


async def test_bad_tool_arguments_go_back_to_the_model(
    runtime: FakeRuntime, script: list[Turn]
) -> None:
    script += [call("what_if_band", volcano_id="263300", base_fl="FL000", top_fl=350)]
    script += [call("exposed_flights"), reply_json(**GROUNDED)]
    result, _ = await ask_with(runtime, GeminiStandIn())
    assert isinstance(result, AskAnswer)
    assert result.tool_calls[0].result_summary.startswith("ERROR")
    assert [item.tool for item in result.evidence] == ["exposed_flights"]


async def test_the_stub_backend_answers_labelled_no_model(runtime: FakeRuntime) -> None:
    result = await answer_question(runtime, StubBackend(), "Anything at all?")
    assert isinstance(result, AskAnswer)
    assert result.llm_backend == "stub"
    assert result.answer.startswith("NO MODEL")
    assert result.claims[0].evidence_ids == ["T01"]
    assert (
        validate_reply(
            result,
            result.evidence,
            question="x",
            airport_icaos=runtime.airports.icaos(),
        )
        == []
    )


async def test_store_ask_keeps_the_record_and_audits_it(runtime: FakeRuntime) -> None:
    answered = await answer_question(runtime, StubBackend(), "Which flights?")
    await store_ask(runtime.store, answered, actor="desk:Ana K")
    doc = await runtime.store.get(Collection.ASK_LOG, answered.id)
    assert doc is not None
    assert AskAnswer.model_validate(doc).question == "Which flights?"
    failed = AskFailure(
        id="ask_000000000000",
        question="q",
        asked_at=AT,
        replay=False,
        reason="AI UNAVAILABLE: budget_exhausted",
        llm_backend="gemini",
        model_id="m",
        prompt_hash="p",
    )
    await store_ask(runtime.store, failed, actor="desk:Ana K")
    stored = await runtime.store.get(Collection.ASK_LOG, failed.id)
    assert stored is not None
    assert stored["status"] == "unavailable"
    entries = await audit.list_entries(runtime.store)
    assert [entry.action for entry in entries] == [AuditAction.ASKED, AuditAction.ASKED]
    assert entries[1].actor == "desk:Ana K"
    assert entries[1].note == "Which flights?"
    assert entries[0].after is not None
    assert entries[0].after["status"] == "unavailable"
    assert await audit.verify_chain(runtime.store) == []


def test_the_prompt_names_every_tool_the_agent_has() -> None:
    prompt = ask.PROMPT_PATH.read_text(encoding="utf-8")
    kit = AskToolkit(cast(Any, SimpleNamespace()))
    for tool in kit.tools():
        assert f"`{tool.__name__}(" in prompt, tool.__name__


# --- voice ------------------------------------------------------------------------------


async def test_transcribe_sends_the_recording_and_returns_the_words() -> None:
    llm = GeminiStandIn()
    llm.heard = [{"text": "  Which flights   enter the cone? ", "language": "en"}]
    transcript = await voice.transcribe(llm, b"RIFF-audio", "audio/webm;codecs=opus")
    assert transcript.text == "Which flights enter the cone?"
    assert (transcript.language, transcript.llm_backend) == ("en", "gemini")
    (part,) = llm.parts[0]
    assert (part.data, part.mime_type) == (b"RIFF-audio", "audio/webm")
    assert part.label == "DISPATCHER VOICE"


@pytest.mark.parametrize(
    ("audio", "mime", "needle"),
    [
        (b"x", "video/mp4", "UNSUPPORTED AUDIO TYPE"),
        (b"", "audio/webm", "BYTES"),
        (b"x" * (voice.MAX_AUDIO_BYTES + 1), "audio/webm", "BYTES"),
    ],
)
async def test_transcribe_refuses_unusable_audio(audio: bytes, mime: str, needle: str) -> None:
    llm = GeminiStandIn()
    with pytest.raises(AiUnavailable, match=needle):
        await voice.transcribe(llm, audio, mime)
    assert llm.parts == []


async def test_transcribe_failures_are_ai_unavailable() -> None:
    with pytest.raises(AiUnavailable, match="AI UNAVAILABLE: api_error 503"):
        await voice.transcribe(GeminiStandIn(), b"x", "audio/webm")
    silent = GeminiStandIn()
    silent.heard = [{"text": "   ", "language": "en"}]
    with pytest.raises(AiUnavailable, match="NO SPEECH RECOGNISED"):
        await voice.transcribe(silent, b"x", "audio/webm")
    long = GeminiStandIn()
    long.heard = [{"text": "word " * 200, "language": "en"}]
    with pytest.raises(AiUnavailable, match="LONGER THAN"):
        await voice.transcribe(long, b"x", "audio/webm")
    with pytest.raises(AiUnavailable, match="NO MODEL"):
        await voice.transcribe(StubBackend(), b"x", "audio/webm")


class FakeTtsClient:
    """``client.aio.models.generate_content`` answering PCM, or raising."""

    def __init__(
        self, *, mime: str = "audio/L16;codec=pcm;rate=24000", error: Exception | None = None
    ):
        self.calls: list[dict[str, Any]] = []
        self._mime = mime
        self._error = error
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    async def _generate(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self._error is not None:
            raise self._error
        inline = SimpleNamespace(data=b"\x01\x00" * 2400, mime_type=self._mime)
        part = SimpleNamespace(inline_data=inline)
        return SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])


async def test_speak_wraps_the_pcm_in_a_wav_header() -> None:
    client = FakeTtsClient()
    llm = GeminiStandIn()
    wav = await voice.speak(
        "Satu penerbangan.",
        "id",
        llm=llm,
        model="tts-model",
        client_factory=lambda: client,
        timeout_s=5.0,
    )
    with wave.open(BytesIO(wav)) as reader:
        assert (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) == (
            1,
            2,
            24000,
        )
        assert reader.getnframes() == 2400
    (sent,) = client.calls
    assert sent["model"] == "tts-model"
    assert sent["contents"] == "Satu penerbangan."
    assert list(sent["config"].response_modalities) == ["AUDIO"]
    assert sent["config"].speech_config.language_code == "id-ID"
    assert llm.reserved == ["lite"]


async def test_speak_failures_are_ai_unavailable() -> None:
    kwargs: dict[str, Any] = {"model": "m", "timeout_s": 5.0}
    broke = genai_errors.ServerError(503, {"error": {"status": "UNAVAILABLE"}})
    with pytest.raises(AiUnavailable, match="api_error 503"):
        await voice.speak(
            "x",
            "en",
            llm=GeminiStandIn(),
            client_factory=lambda: FakeTtsClient(error=broke),
            **kwargs,
        )
    with pytest.raises(AiUnavailable, match="budget_exhausted"):
        await voice.speak(
            "x",
            "en",
            llm=GeminiStandIn(budget_left=False),
            client_factory=lambda: FakeTtsClient(),
            **kwargs,
        )
    with pytest.raises(AiUnavailable, match="UNEXPECTED AUDIO TYPE"):
        await voice.speak(
            "x",
            "en",
            llm=GeminiStandIn(),
            client_factory=lambda: FakeTtsClient(mime="audio/mpeg"),
            **kwargs,
        )
    with pytest.raises(AiUnavailable, match="NO MODEL"):
        await voice.speak(
            "x", "en", llm=StubBackend(), client_factory=lambda: FakeTtsClient(), **kwargs
        )
    with pytest.raises(AiUnavailable, match="TEXT TO SPEAK"):
        await voice.speak(
            "", "en", llm=GeminiStandIn(), client_factory=lambda: FakeTtsClient(), **kwargs
        )
    quota = genai_errors.ClientError(
        429,
        {
            "error": {
                "status": "RESOURCE_EXHAUSTED",
                "details": [{"violations": [{"quotaId": "PerDay"}]}],
            }
        },
    )
    llm = GeminiStandIn()
    with pytest.raises(AiUnavailable):
        await voice.speak(
            "x", "en", llm=llm, client_factory=lambda: FakeTtsClient(error=quota), **kwargs
        )
    assert llm.exhausted == ["lite"]


def test_speech_cache_keeps_the_most_recent_answers() -> None:
    cache = voice.SpeechCache(size=2)
    cache.put("a", b"1")
    cache.put("b", b"2")
    assert cache.get("a") == b"1"
    cache.put("c", b"3")
    assert (cache.get("a"), cache.get("b"), cache.get("c")) == (b"1", None, b"3")


# --- routes -----------------------------------------------------------------------------


class RecordingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, Any]] = []

    def publish(self, name: Any, data: Any) -> Any:
        self.events.append((str(name), data))
        return super().publish(name, data)


@pytest.fixture
def api(tmp_path: Path) -> Iterator[tuple[TestClient, FakeRuntime]]:
    built = make_runtime(tmp_path, llm=StubBackend())
    built.bus = RecordingBus()

    async def factory(_: Settings) -> Any:
        return built

    app = create_app(built.settings, runtime_factory=factory)
    app.include_router(routes_ask.router, prefix="/api")
    with TestClient(app) as client, use_clock(FixedClock(AT)):
        yield client, built


def login(client: TestClient) -> None:
    response = client.post("/api/desk/login", json={"pin": PIN, "name": "Ana K"})
    assert response.status_code == 200


def test_ask_needs_a_desk_session_and_a_csrf_proof(api: tuple[TestClient, FakeRuntime]) -> None:
    client, _ = api
    assert client.post("/api/desk/ask", json={"question": "Which flights?"}).status_code == 401
    login(client)
    forged = client.post(
        "/api/desk/ask", content=b'{"question":"x"}', headers={"content-type": "text/plain"}
    )
    assert forged.status_code == 403
    assert client.post("/api/desk/ask", json={"question": ""}).status_code == 422
    assert client.post("/api/desk/ask", json={"question": "x" * 501}).status_code == 422
    assert (
        client.post("/api/desk/ask", json={"question": "q", "flight_id": "a b"}).status_code == 422
    )


def test_ask_answers_stores_audits_and_reports_the_budget(
    api: tuple[TestClient, FakeRuntime],
) -> None:
    client, runtime = api
    login(client)
    response = client.post("/api/desk/ask", json={"question": "Which flights?"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "answered"
    assert body["llm_backend"] == "stub"
    assert body["evidence"][0]["id"] == "T01"
    assert body["tool_calls"][0]["name"] == "exposed_flights"
    events = cast(RecordingBus, runtime.bus).events
    assert [name for name, _ in events if name == SseEvent.BUDGET.value] == ["budget"]
    assert any("NO MODEL" in message for message in runtime.traces)


async def test_ask_failure_is_a_503_with_the_ai_unavailable_message(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, llm=GeminiStandIn(budget_left=False))

    async def factory(_: Settings) -> Any:
        return runtime

    app = create_app(runtime.settings, runtime_factory=factory)
    app.include_router(routes_ask.router, prefix="/api")
    with TestClient(app) as client:
        login(client)
        response = client.post("/api/desk/ask", json={"question": "Which flights?"})
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "ai_unavailable"
    assert body["message"] == body["detail"] == "AI UNAVAILABLE: budget_exhausted"
    stored = await open_store(runtime.settings).list_docs(Collection.ASK_LOG)
    assert [doc["status"] for doc in stored] == ["unavailable"]


def test_budget_is_public_and_reads_the_days_counts(
    api: tuple[TestClient, FakeRuntime],
) -> None:
    client, runtime = api
    body = client.get("/api/budget").json()
    assert body["backend"] == "stub"
    assert {tier["tier"]: tier["limit"] for tier in body["tiers"]} == {
        "main": runtime.settings.model_daily_budget,
        "lite": runtime.settings.model_lite_daily_budget,
    }
    assert all(tier["used"] == 0 for tier in body["tiers"])


async def test_budget_view_counts_gemini_calls_from_the_budget_file(tmp_path: Path) -> None:
    from tephra.agents.llm import BUDGET_FILE, DailyBudget

    settings = Settings(_env_file=None, cache_dir=tmp_path / "cache")
    budget = DailyBudget(path=settings.cache_dir / "llm" / BUDGET_FILE)
    budget.take("lite", 10)
    budget.take("lite", 10)
    budget.take("main", 10)
    view = await routes_ask.budget_view(settings, GeminiStandIn())
    tiers = {tier.tier: tier for tier in view.tiers}
    assert (tiers["lite"].used, tiers["lite"].remaining) == (
        2,
        settings.model_lite_daily_budget - 2,
    )
    assert (tiers["main"].used, tiers["main"].model_id) == (1, SCRIPTED_MODEL)
    assert view.backend == "gemini"


def test_voice_route_transcribes_then_answers(
    api: tuple[TestClient, FakeRuntime], script: list[Turn]
) -> None:
    client, runtime = api
    llm = GeminiStandIn()
    llm.heard = [{"text": "Which flights enter the cone?", "language": "en"}]
    runtime.llm = llm
    script += [call("exposed_flights"), reply_json(**GROUNDED)]
    login(client)

    response = client.post(
        "/api/desk/ask/voice",
        files={"audio": ("ask.webm", b"audio-bytes", "audio/webm")},
        data={"flight_id": "8a01f2:263300"},
        headers={"x-tephra-desk": "1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"]["text"] == "Which flights enter the cone?"
    assert body["answer"]["question"] == "Which flights enter the cone?"
    assert body["answer"]["flight_id"] == "8a01f2:263300"


def test_voice_route_limits_and_failures(api: tuple[TestClient, FakeRuntime]) -> None:
    client, runtime = api
    login(client)
    headers = {"x-tephra-desk": "1"}
    stub = client.post(
        "/api/desk/ask/voice", files={"audio": ("a.webm", b"x", "audio/webm")}, headers=headers
    )
    assert stub.status_code == 503
    assert stub.json()["message"].startswith("AI UNAVAILABLE: NO MODEL")
    runtime.llm = GeminiStandIn()
    wrong_type = client.post(
        "/api/desk/ask/voice", files={"audio": ("a.txt", b"x", "text/plain")}, headers=headers
    )
    assert wrong_type.status_code == 503
    assert "UNSUPPORTED AUDIO TYPE" in wrong_type.json()["message"]


def test_a_voice_answer_that_fails_still_shows_what_was_heard(
    api: tuple[TestClient, FakeRuntime], script: list[Turn]
) -> None:
    client, runtime = api
    llm = GeminiStandIn(budget_left=False)
    llm.heard = [{"text": "Which flights?", "language": "en"}]
    runtime.llm = llm
    login(client)
    response = client.post(
        "/api/desk/ask/voice",
        files={"audio": ("a.webm", b"x", "audio/webm")},
        headers={"x-tephra-desk": "1"},
    )
    assert response.status_code == 503
    assert response.json()["problems"] == ["transcript: Which flights?"]


def test_speak_route_speaks_a_stored_answer_once(api: tuple[TestClient, FakeRuntime]) -> None:
    client, runtime = api
    login(client)
    answer_id = client.post("/api/desk/ask", json={"question": "Which flights?"}).json()["id"]
    runtime.llm = GeminiStandIn()
    tts = FakeTtsClient()
    client.app.state.tts_client = tts  # type: ignore[attr-defined]

    first = client.post("/api/desk/ask/speak", json={"answer_id": answer_id})
    second = client.post("/api/desk/ask/speak", json={"answer_id": answer_id})

    assert first.status_code == 200
    assert first.headers["content-type"] == "audio/wav"
    assert first.content[:4] == b"RIFF"
    assert second.content == first.content
    assert len(tts.calls) == 1
    assert tts.calls[0]["model"] == Settings(_env_file=None).model_tts
    assert "NO MODEL" in tts.calls[0]["contents"]


def test_speak_route_errors(api: tuple[TestClient, FakeRuntime]) -> None:
    client, runtime = api
    login(client)
    assert client.post("/api/desk/ask/speak", json={"answer_id": "nope"}).status_code == 422
    assert (
        client.post("/api/desk/ask/speak", json={"answer_id": "ask_000000000000"}).status_code
        == 404
    )
    answer_id = client.post("/api/desk/ask", json={"question": "q"}).json()["id"]
    unavailable = client.post("/api/desk/ask/speak", json={"answer_id": answer_id})
    assert unavailable.status_code == 503
    assert unavailable.json()["message"].startswith("AI UNAVAILABLE: NO MODEL")
    runtime.llm = GeminiStandIn()
    client.app.state.tts_client = FakeTtsClient(  # type: ignore[attr-defined]
        error=genai_errors.ServerError(503, {"error": {"status": "UNAVAILABLE"}})
    )
    broken = client.post("/api/desk/ask/speak", json={"answer_id": answer_id})
    assert broken.status_code == 503
    assert "api_error 503" in broken.json()["message"]


def test_a_recording_is_an_audio_part_sent_as_bytes_with_its_mime_type() -> None:
    from tephra.agents import llm as llm_module

    recording = LlmPart.of_audio(b"\x01\x02\x03", label="DISPATCHER VOICE", mime_type="audio/webm")
    assert recording.kind == "audio"
    contents = llm_module._contents([recording, LlmPart.of_text("ask")])
    assert len(contents) == 2  # no "IMAGE <label>" announcement for audio
    assert contents[0].inline_data is not None
    assert contents[0].inline_data.mime_type == "audio/webm"
    assert contents[0].inline_data.data == b"\x01\x02\x03"
    config = llm_module._config("system", [recording], voice._Heard, 0.0)
    assert config.media_resolution is None  # only images set a media resolution

    same = llm_module.prompt_hash("s", [recording])
    other = llm_module.prompt_hash(
        "s", [LlmPart.of_audio(b"\x01\x02\x04", label="DISPATCHER VOICE", mime_type="audio/webm")]
    )
    as_image = llm_module.prompt_hash(
        "s", [LlmPart.of_image(b"\x01\x02\x03", label="DISPATCHER VOICE", mime_type="audio/webm")]
    )
    assert len({same, other, as_image}) == 3
