"""SRA and VAR drafts: evidence by code, checked narrative boxes, blanks left blank, sign-off.

No network and no live model: a scripted LlmBackend stands in for Gemini, the store is a real
SQLite file under ``tmp_path``, and the clock is fixed.
"""

import json
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from tephra.agents.llm import LlmCall, LlmPart, prompt_hash
from tephra.api.routes_regdocs import router
from tephra.api.server import create_app
from tephra.config import NO_MODEL_LABEL, PROJECT_ROOT, REGIONS, Settings
from tephra.desk import audit
from tephra.duty import _RuntimeExecutor
from tephra.geo.fuel import category_for_type, hold_line
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryStatus,
    AirlineInfo,
    AuditAction,
    AviationColor,
    Discrepancy,
    DiscrepancyKind,
    ExposedFlight,
    FeedHealth,
    FeedId,
    FeedStatus,
    HazardCone,
    LlmBackendName,
    LlmInfo,
    OfficialLayer,
    OperatorPolicy,
    PlumeMode,
    PolicySummary,
    Provenance,
    RunMode,
    Sigmet,
    Situation,
    SseEvent,
    SystemState,
    TickReport,
    TraceActor,
    TraceEvent,
    TraceStage,
    VaacCentre,
    Volcano,
    Vona,
    polygon_from_latlon,
)
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.regdocs.evidence import NoActiveVolcano, UnknownRegion, gather_evidence
from tephra.regdocs.models import (
    SRA_HEADER,
    VAR_HEADER,
    DocKind,
    DocStatus,
    NarrativeBox,
    SignRole,
    SraDraft,
    SraNarrative,
)
from tephra.regdocs.narrative import (
    NARRATIVE_MAX_CHARS,
    AiUnavailable,
    stub_narrative,
    validate_narrative,
)
from tephra.regdocs.registry import (
    AlreadySigned,
    DocNotFound,
    InvalidSignature,
    get_doc,
    list_docs,
    sign_doc,
)
from tephra.regdocs.sra import DOC_9974, draft_sra, narrative_facts
from tephra.regdocs.var import FlightNotExposed, draft_var, format_position
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.hashing import proxy_flight_number
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)
SHA = "ab" * 32
POLICY = load_policy(PROJECT_ROOT / "data")
VOLCANO_ID = "263300"
SIGMET_ID = "SIGMET:WAAF:3:20261009T1800Z"
VONA_ID = "VONA:22880"
CONE_ID = "CONE-0123456789ab"
HEX = "8a0123"
FLIGHT_ID = f"{HEX}:{VOLCANO_ID}"
PROXY = proxy_flight_number(HEX)
ADVISORY_ID = "adv_0123456789ab"
PIN = "zulu-4711"
DISPATCHER = "Ana K"

SEMERU = Volcano(
    id=VOLCANO_ID,
    name="Semeru",
    magma_code="SMR",
    country="Indonesia",
    lat=-8.108,
    lon=112.922,
    summit_elev_m=3676,
    observatory="PVMBG",
    vaac=VaacCentre.DARWIN,
)
AREA = polygon_from_latlon([(-8.0, 112.8), (-8.0, 113.4), (-8.4, 113.4), (-8.4, 112.8)])


@pytest.fixture(autouse=True)
def fixed_clock() -> Iterator[None]:
    with use_clock(FixedClock(AT)):
        yield


# --- fixtures: a picture, a flight, a runtime -------------------------------------------


def provenance(source_id: str, feed: FeedId, issued: datetime) -> Provenance:
    return Provenance(
        source_id=source_id,
        feed=feed,
        url="https://example.invalid/feed",
        fetched_at=AT,
        issued_at=issued,
        sha256=SHA,
    )


def make_situation(volcano: Volcano = SEMERU) -> Situation:
    sigmet = Sigmet(
        provenance=provenance(SIGMET_ID, FeedId.SIGMET, AT - timedelta(hours=1)),
        fir_id="WAAF",
        series_id="3",
        volcano_name="SEMERU",
        base_ft=0,
        top_ft=15_000,
        polygon=AREA,
        valid_from=AT - timedelta(hours=1),
        valid_to=AT + timedelta(hours=5),
        raw_text="WAAF SIGMET 3 VALID 091800/100000 VA ERUPTION MT SEMERU",
    )
    vona = Vona(
        provenance=provenance(VONA_ID, FeedId.VONA, AT - timedelta(minutes=50)),
        volcano_name="Semeru",
        issued_at=AT - timedelta(minutes=50),
        color_code=AviationColor.ORANGE,
        ash_observed=True,
        cloud_top_ft=10_000,
        raw_text="VONA text",
    )
    layer = OfficialLayer(
        source_id=SIGMET_ID,
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WAAF 3",
        volcano_id=volcano.id,
        polygon=AREA,
        base_ft=0,
        top_ft=15_000,
        valid_from=AT - timedelta(hours=1),
        valid_to=AT + timedelta(hours=5),
    )
    conflict = Discrepancy(
        id="D-0123abcd",
        volcano_id=volcano.id,
        kind=DiscrepancyKind.HEIGHT_MISMATCH,
        aspect="top",
        source_ids=[SIGMET_ID, VONA_ID],
        values={SIGMET_ID: "FL150", VONA_ID: "FL100"},
        magnitude=5000,
        unit="ft",
        summary="SIGMET top FL150 against VONA top FL100",
    )
    return Situation(
        volcano=volcano,
        as_of=AT,
        mode=RunMode.LIVE,
        active_reasons=["VA SIGMET valid"],
        sigmets=[sigmet],
        vonas=[vona],
        official_layers=[layer],
        discrepancies=[conflict],
    )


def make_cone(mode: PlumeMode = PlumeMode.OFFICIAL) -> HazardCone:
    return HazardCone(
        id=CONE_ID,
        volcano_id=VOLCANO_ID,
        assessment_id="PA-0123456789ab",
        mode=mode,
        confidence=0.8,
        llm_backend="stub",
        created_at=AT,
        horizon_h=6,
        valid_to=AT + timedelta(hours=6),
        geometry=AREA,
        base_ft=0,
        top_ft=15_000,
        official_source_ids=[SIGMET_ID],
    )


def make_flight(*, inside: bool = False, alt_ft: int | None = 12_000) -> ExposedFlight:
    category = category_for_type("B738")
    return ExposedFlight(
        id=FLIGHT_ID,
        hex=HEX,
        callsign="GIA417",
        proxy_flight=PROXY,
        type_icao="B738",
        category=category,
        lat=-8.15,
        lon=113.70,
        alt_baro_ft=alt_ft,
        gs_kt=420.0,
        track_deg=270.0,
        observed_at=AT,
        source_id="ADSB:-8.200:113.600:20261009T193800Z",
        volcano_id=VOLCANO_ID,
        cone_id=CONE_ID,
        inside_now=inside,
        minutes_to_entry=0 if inside else 9,
        entry_lat=-8.15,
        entry_lon=113.4,
        aircraft_band_ft=(alt_ft or 0, alt_ft or 0),
        hazard_band_ft=(0, 15_000),
        path=[(113.7, -8.15), (113.4, -8.15)],
        hold=hold_line(category, minutes=POLICY.fuel.hold_min.value),
    )


def make_advisory() -> Advisory:
    return Advisory(
        id=ADVISORY_ID,
        version=1,
        status=AdvisoryStatus.DRAFT,
        created_at=AT,
        updated_at=AT,
        replay=False,
        volcano_id=VOLCANO_ID,
        volcano_name="Semeru",
        flight_id=FLIGHT_ID,
        proxy_flight=PROXY,
        callsign="GIA417",
        hex=HEX,
        type_icao="B738",
        action=ActionKind.CHANGE_LEVEL,
        change_level_fl_min=180,
        change_level_fl_max=200,
        minutes_to_entry=9,
        inside_now=False,
        fuel_line="",
        plume_mode=PlumeMode.OFFICIAL,
        confidence=0.8,
        cone_id=CONE_ID,
        assessment_id="PA-0123456789ab",
        plan_id="PLAN-0123456789ab",
        header="TEPHRA COMPANY ADVISORY",
        body="CLIMB TO FL180-FL200",
        cost_note="",
        sources=[],
        input_hash="0" * 64,
        llm_backend="stub",
        model_id="stub",
        prompt_hashes={"plume_reader": "a" * 64, "planner": "b" * 64, "drafter": "c" * 64},
        dedupe_key="DD-0123456789ab",
    )


class ScriptedLlm:
    """A minimal LlmBackend. ``stub`` mode returns the caller's stub; otherwise it plays
    ``script`` in order, where None is a model that gave nothing."""

    def __init__(
        self,
        name: LlmBackendName = "stub",
        script: list[SraNarrative | None] | None = None,
    ) -> None:
        self.name: LlmBackendName = name
        self.script = script or []
        self.calls = 0

    def model_id(self, tier: str) -> str:
        return "stub" if self.name == "stub" else "gemini-test-lite"

    async def pace(self, tier: str, tokens: int = 0) -> None:
        return None

    async def reserve(self, tier: str) -> str | None:
        return None

    async def exhaust(self, tier: str) -> None:
        raise AssertionError("the documents never close a tier themselves")

    async def structured[T: BaseModel](
        self,
        *,
        tier: str,
        system: str,
        parts: Sequence[LlmPart],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        self.calls += 1
        value: Any = stub() if self.name == "stub" else self.script.pop(0)
        call = LlmCall(
            backend=self.name,
            model_id=self.model_id(tier),
            prompt_hash=prompt_hash(system, parts),
            raw_text=None if value is None else value.model_dump_json(),
            error=None if value is not None else "api_error 503 UNAVAILABLE",
        )
        return value, call


@dataclass
class FakeRuntime:
    settings: Settings
    store: Store
    llm: ScriptedLlm
    bus: EventBus = field(default_factory=EventBus)
    policy: OperatorPolicy = field(default_factory=lambda: POLICY)
    policy_summary: PolicySummary = field(default_factory=lambda: PolicySummary.of(POLICY))
    mode: RunMode = RunMode.LIVE
    situations: dict[str, Situation] = field(default_factory=dict)
    cones: dict[str, HazardCone] = field(default_factory=dict)
    exposed: dict[str, ExposedFlight] = field(default_factory=dict)
    traces: list[tuple[TraceStage, str, str]] = field(default_factory=list)

    def aircraft(self) -> list[Any]:
        return []

    async def aclose(self) -> None:
        await self.store.aclose()

    async def system_state(self) -> SystemState:
        return SystemState(
            mode=self.mode,
            now=AT,
            server_time=AT,
            llm=LlmInfo(backend="stub", model_id="stub", label=NO_MODEL_LABEL),
            airline=AirlineInfo(code="RFA", name="Ring of Fire Air"),
            disclaimer="Decision support only",
            region=self.settings.region_preset,
            regions=self.settings.regions,
            feeds=[
                FeedHealth(
                    feed=FeedId.SIGMET,
                    status=FeedStatus.OK,
                    cadence_s=60,
                    last_success_at=AT,
                    age_s=90,
                )
            ],
            active_volcano_ids=[VOLCANO_ID],
            exposed_count=len(self.exposed),
            draft_count=0,
            policy=self.policy_summary,
        )

    def trace(
        self,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: str = "info",
        volcano_id: str | None = None,
        flight_id: str | None = None,
        detail: Any = None,
    ) -> TraceEvent:
        self.traces.append((stage, level, message))
        return TraceEvent.new(stage, actor, message, level=cast(Any, level), detail=detail)


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=PROJECT_ROOT / "data",
        desk_pin=PIN,
        task_token="task-token-for-tests-0123456789abcdef",
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


async def make_runtime(
    tmp_path: Path, llm: ScriptedLlm | None = None, *, inside: bool = False
) -> FakeRuntime:
    settings = make_settings(tmp_path)
    store = open_store(settings)
    runtime = FakeRuntime(
        settings=settings,
        store=store,
        llm=llm or ScriptedLlm(),
        situations={VOLCANO_ID: make_situation()},
        cones={VOLCANO_ID: make_cone()},
        exposed={FLIGHT_ID: make_flight(inside=inside)},
    )
    assert await store.compare_and_set_advisory(
        ADVISORY_ID, 0, make_advisory().model_dump(mode="json")
    )
    return runtime


@pytest.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[FakeRuntime]:
    made = await make_runtime(tmp_path)
    yield made
    await made.store.aclose()


def good_narrative(**changes: NarrativeBox) -> SraNarrative:
    box = NarrativeBox(
        text="Semeru has an official area and a TEPHRA cone; the official area stays binding.",
        source_ids=[SIGMET_ID],
    )
    base = {
        "information_sources": box,
        "hazard_summary": box,
        "exposure_summary": box,
        "mitigation_summary": box,
    }
    return SraNarrative(**{**base, **changes})


def all_fields(doc: SraDraft) -> dict[str, Any]:
    return {(section.key, field.key): field for section in doc.sections for field in section.fields}


# --- the SRA draft ----------------------------------------------------------------------


async def test_sra_is_filled_by_code_and_labelled_a_draft(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")

    assert doc.header == SRA_HEADER == "DRAFT - NOT AN APPROVED SRA - FOR HUMAN SIGN-OFF"
    assert doc.status is DocStatus.DRAFT
    assert NO_MODEL_LABEL in doc.labels
    assert any("FICTIONAL" in label for label in doc.labels)
    assert [section.number for section in doc.sections] == list(range(12))
    assert (doc.llm_backend, doc.model_id) == ("stub", "stub")
    assert doc.policy_id == POLICY.policy_id
    assert doc.volcano_ids == [VOLCANO_ID]
    assert {line.role for line in doc.signatures} == {
        SignRole.DISPATCHER,
        SignRole.SAFETY_MANAGER,
        SignRole.ACCOUNTABLE_EXECUTIVE,
    }


async def test_sra_leaves_what_tephra_cannot_know_blank(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")
    fields = all_fields(doc)

    for key in (("status", "accountable"), ("status", "acceptance"), ("scope", "aoc")):
        assert fields[key].blank
        assert fields[key].origin == "human"
    worksheet = next(s for s in doc.sections if s.key == "worksheet").tables[0]
    assert len(worksheet.rows) >= 5
    for row in worksheet.rows:
        assert row[4:] == [None] * 6  # severity, probability, tolerability, actions, after
        assert row[3]  # existing controls are written
    assert "2000" in worksheet.rows[0][3]  # the policy's vertical margin, not a literal


async def test_sra_tables_carry_the_evidence(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")
    section = {item.key: item for item in doc.sections}

    sources = section["sources"].tables[0].rows
    assert [row[1] for row in sources] == [SIGMET_ID, VONA_ID]
    conflicts = section["sources"].tables[1].rows
    assert conflicts[0][1:4] == ["HEIGHT_MISMATCH", "top", "CAUTION"]
    hazard = section["hazard"].tables[0].rows[0]
    assert hazard[:2] == ["Semeru", "OFFICIAL"]
    assert hazard[4] == "SFC/FL150"
    assert hazard[6:] == ["ORANGE", "FL100"]
    exposure = section["exposure"].tables[0].rows[0]
    assert exposure[0] == PROXY
    assert exposure[3] == "entry in 9 min"
    assert exposure[6] == str(POLICY.exposure.vertical_margin_ft.value)
    decision = section["mitigation"].tables[0].rows[0]
    assert decision[1:3] == ["CHANGE_LEVEL", "FL180-FL200"]
    assert decision[3] is None  # MEL relief is the dispatcher's
    assert decision[5:] == [ADVISORY_ID, "DRAFT"]


async def test_the_four_boxes_are_marked_ai_written_with_their_ids(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")
    boxes = [field for field in all_fields(doc).values() if field.origin == "ai"]

    assert {box.key for box in boxes} == {
        "information_sources",
        "hazard_summary",
        "exposure_summary",
        "mitigation_summary",
    }
    assert all(box.source_ids and set(box.source_ids) <= set(doc.source_ids) for box in boxes)


async def test_indonesia_overlay_says_it_rests_on_press_reports(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")
    overlay = next(section for section in doc.sections if section.key == "indonesia")

    assert "SE-DJPU 15/2026" in overlay.title
    assert "per press reports of the circular; verify against the PDF" in overlay.reference
    assert "Check it against the PDF" in overlay.fields[0].value
    assert len(overlay.tables[0].rows) == 5
    assert all(row[2] is None for row in overlay.tables[0].rows)  # done: for a person to tick
    assert "72" not in json.dumps(overlay.model_dump(mode="json"))  # no deadline is invented


async def test_doc_9974_is_cited_as_first_edition_2012(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali")
    text = json.dumps(doc.model_dump(mode="json"))

    assert DOC_9974 == "ICAO Doc 9974, Flight Safety and Volcanic Ash, First Edition 2012"
    assert DOC_9974 in text
    assert "second edition" not in text.lower()
    assert "2nd" not in text


async def test_sra_is_stored_audited_and_announced(runtime: FakeRuntime) -> None:
    doc = await draft_sra(runtime, "java_bali", actor="desk:Ana K")

    stored = await get_doc(runtime.store, doc.id)
    assert isinstance(stored, SraDraft)
    assert stored.id == doc.id
    [entry] = [
        item
        for item in await audit.list_entries(runtime.store)
        if item.action is AuditAction.DOC_DRAFTED
    ]
    assert entry.actor == "desk:Ana K"
    assert entry.after is not None
    assert entry.after["doc_id"] == doc.id
    assert entry.input_hashes == [doc.input_hash]
    [event] = runtime.bus.recent(SseEvent.DOC)
    assert event.data["id"] == doc.id
    assert runtime.traces[-1][0] is TraceStage.DOCS
    assert await audit.verify_chain(runtime.store) == []


async def test_a_replay_sra_says_so(tmp_path: Path) -> None:
    runtime = await make_runtime(tmp_path)
    runtime.mode = RunMode.REPLAY
    advisory = make_advisory().model_copy(update={"replay": True})
    await runtime.store.put(Collection.ADVISORIES, ADVISORY_ID, advisory.model_dump(mode="json"))
    doc = await draft_sra(runtime, "java_bali")
    assert doc.replay
    await runtime.store.aclose()


async def test_the_duty_officer_drafts_no_second_sra_while_one_waits(
    runtime: FakeRuntime,
) -> None:
    """One unsigned SRA draft per region and mode: the day's mark is held in memory, so a replay
    run or a restart offers the region again, and gets the waiting draft back, not one more."""
    first = await draft_sra(runtime, "java_bali")
    runtime.sra_drafted = set()  # a fresh picture: the in-memory mark is gone
    report = TickReport(started_at=AT, finished_at=AT, mode=RunMode.LIVE, reason="manual")
    executor = _RuntimeExecutor(runtime, AT, report, {}, 0)  # type: ignore[arg-type]

    result = await executor.draft_sra("java_bali")

    assert result["doc_id"] == first.id
    assert [doc.id for doc in await list_docs(runtime.store, kind=DocKind.SRA)] == [first.id]
    runtime.mode = RunMode.REPLAY  # a replay's SRA is its own: the live draft does not stand in
    assert (await executor.draft_sra("java_bali"))["doc_id"] != first.id


async def test_unknown_region_and_a_quiet_region_are_refused(runtime: FakeRuntime) -> None:
    with pytest.raises(UnknownRegion):
        await draft_sra(runtime, "atlantis")
    with pytest.raises(NoActiveVolcano):
        await draft_sra(runtime, "kyushu")
    assert runtime.llm.calls == 0  # nothing to assess: no model call is spent


# --- narrative checks and the no-fallback path ------------------------------------------


async def evidence_facts(runtime: FakeRuntime) -> dict[str, Any]:
    return narrative_facts(await gather_evidence(runtime, "java_bali"), POLICY)


def box(text: str, ids: list[str] | None = None) -> NarrativeBox:
    return NarrativeBox(text=text, source_ids=[SIGMET_ID] if ids is None else ids)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Issued at 1830Z by the office.", "CLOCK TIME"),
        ("The cone reaches FL410 over Semeru.", "NUMBERS NOT IN THE FACTS: 410"),
        (f"Product {SIGMET_ID} shows the area.", "WRITES AN ID"),
        ("See SIGMET:WAAF:9:20261009T2000Z for it.", "WRITES AN ID"),
        ("Divert to WIII if needed.", "NAMES WIII"),
        ("Flight RFA9999 is exposed.", "NAMES RFA9999"),
        ("The operation is safe at this level.", "CLAIM"),
        ("The ash has dispersed over Semeru.", "CLAIM"),
        ("There is no ash left.", "CLAIM"),
        ("x" * (NARRATIVE_MAX_CHARS + 1), "THE LIMIT IS"),
        ("   ", "IS EMPTY"),
    ],
)
async def test_the_validator_rejects(runtime: FakeRuntime, text: str, expected: str) -> None:
    facts = await evidence_facts(runtime)
    problems = validate_narrative(good_narrative(hazard_summary=box(text)), facts)
    assert any(expected in problem for problem in problems), problems


async def test_the_validator_rejects_an_unknown_source_id(runtime: FakeRuntime) -> None:
    facts = await evidence_facts(runtime)
    narrative = good_narrative(hazard_summary=box("Semeru is erupting.", ["SIGMET:NOPE:1"]))
    assert any("NOT IN allowed_ids" in p for p in validate_narrative(narrative, facts))


async def test_the_validator_accepts_numbers_and_flights_from_the_facts(
    runtime: FakeRuntime,
) -> None:
    facts = await evidence_facts(runtime)
    text = f"{PROXY} is exposed to the SFC/FL150 area, with a margin of 2000 ft. Per VONA data."
    assert validate_narrative(good_narrative(exposure_summary=box(text)), facts) == []
    assert validate_narrative(stub_narrative(facts), facts) == []


async def test_facts_for_the_model_hold_no_clock_times(runtime: FakeRuntime) -> None:
    facts = await evidence_facts(runtime)
    text = json.dumps(facts)
    for known in facts["allowed_ids"]:
        text = text.replace(known, "ID")  # ids carry times; the text boxes may not
    assert "2026-10" not in text
    assert "1800Z" not in text


async def test_a_repair_is_allowed_once(tmp_path: Path) -> None:
    bad = good_narrative(hazard_summary=box("The cone reaches FL410."))
    llm = ScriptedLlm("gemini", [bad, good_narrative()])
    runtime = await make_runtime(tmp_path, llm)

    doc = await draft_sra(runtime, "java_bali")

    assert llm.calls == 2
    assert doc.llm_backend == "gemini"
    assert NO_MODEL_LABEL not in doc.labels
    await runtime.store.aclose()


async def test_no_usable_answer_is_ai_unavailable_and_stores_nothing(tmp_path: Path) -> None:
    bad = good_narrative(hazard_summary=box("The cone reaches FL410."))
    llm = ScriptedLlm("gemini", [bad, bad])
    runtime = await make_runtime(tmp_path, llm)

    with pytest.raises(AiUnavailable) as caught:
        await draft_sra(runtime, "java_bali")

    assert str(caught.value).startswith("AI UNAVAILABLE: NARRATIVE FAILED CHECKS AFTER REPAIR")
    assert llm.calls == 2
    assert await list_docs(runtime.store) == []
    [entry] = [
        item
        for item in await audit.list_entries(runtime.store)
        if item.action is AuditAction.AI_FAILED
    ]
    assert entry.note is not None
    assert entry.note.startswith("AI UNAVAILABLE")
    assert runtime.traces[-1][1] == "error"
    await runtime.store.aclose()


async def test_a_model_that_gives_nothing_is_not_asked_again(tmp_path: Path) -> None:
    llm = ScriptedLlm("gemini", [None])
    runtime = await make_runtime(tmp_path, llm)

    with pytest.raises(AiUnavailable, match=r"AI UNAVAILABLE: NO NARRATIVE RETURNED \(api_error"):
        await draft_sra(runtime, "java_bali")

    assert llm.calls == 1
    await runtime.store.aclose()


# --- the VAR draft ----------------------------------------------------------------------


def test_positions_are_written_in_degrees_and_minutes() -> None:
    assert format_position(-8.15, 113.70) == "0809S11342E"
    assert format_position(10.9999, -0.4) == "1100N00024W"
    assert format_position(31.9, 130.6) == "3154N13036E"


async def test_var_fills_items_1_to_5_and_leaves_6_to_16_blank(runtime: FakeRuntime) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)

    assert doc.header == VAR_HEADER
    assert runtime.llm.calls == 0  # no model writes crew observations
    by_number = {item.number: item for item in doc.items}
    assert sorted(by_number) == list(range(1, 17))
    assert [by_number[n].value for n in (1, 2, 3, 4)] == [PROXY, "0809S11342E", "1940Z", "FL120"]
    assert not by_number[5].blank
    assert by_number[5].origin == "code"
    assert "NOT a crew observation" in (by_number[5].note or "")
    assert "bearing" in (by_number[5].value or "")
    assert "Official ash top FL150" in (by_number[5].value or "")
    for number in range(6, 17):
        item = by_number[number]
        assert item.blank
        assert item.origin == "human"
        assert item.note == "PILOT/DISPATCHER TO COMPLETE"
    assert {item.group for item in doc.items if item.number >= 9} == {"post_flight"}


async def test_var_header_blanks_and_proxy_label(runtime: FakeRuntime) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)
    fields = {item.key: item for item in doc.header_fields}

    assert fields["pic"].blank
    assert fields["dep"].blank
    assert fields["arr"].blank
    assert "ADS-B callsign GIA417" in (fields["ac_ident"].note or "")
    assert doc.labels[0].startswith("ADS-B PROXY FLIGHT")
    assert doc.non_encounter.blank
    assert "@" not in json.dumps(doc.model_dump(mode="json"))  # no e-mail address is written


async def test_var_airep_special_and_ars_lines(runtime: FakeRuntime) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)

    assert doc.airep_special.value == (
        f"AIREP SPECIAL {PROXY} 0809S11342E 1940 FL120 VOLCANIC ASH CLOUD"
    )
    assert "does not know whether the crew saw ash" in (doc.airep_special.note or "")
    assert doc.ars_line.value == f"ARS {PROXY} 0809S11342E 1940 F120 VA CLD="


async def test_var_without_an_adsb_level_leaves_the_level_and_lines_blank(
    runtime: FakeRuntime,
) -> None:
    runtime.exposed[FLIGHT_ID] = make_flight(alt_ft=None)
    doc = await draft_var(runtime, FLIGHT_ID)

    assert next(item for item in doc.items if item.number == 4).blank
    assert doc.airep_special.blank
    assert doc.ars_line.blank


async def test_var_followups_name_the_indonesian_circular_only_for_indonesia(
    runtime: FakeRuntime,
) -> None:
    indonesian = await draft_var(runtime, FLIGHT_ID)
    assert any(
        "SE-DJPU 15/2026" in step and "press reports" in step for step in indonesian.followups
    )
    assert any("inspected" in step for step in indonesian.followups)

    runtime.situations[VOLCANO_ID] = make_situation(SEMERU.model_copy(update={"country": "Japan"}))
    japanese = await draft_var(runtime, FLIGHT_ID)
    assert not any("SE-DJPU" in step for step in japanese.followups)


async def test_var_context_lists_the_hazard_and_the_issue_times(runtime: FakeRuntime) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)
    context = {item.key: item for item in doc.context}

    assert (
        context["exposure"].value == "enters the hazard area in 9 min if track and level are held"
    )
    assert "SFC/FL150" in (context["official"].value or "")
    assert context["official"].source_ids == [SIGMET_ID]
    assert SIGMET_ID in (context["sources"].value or "")


async def test_var_for_a_flight_that_is_not_exposed(runtime: FakeRuntime) -> None:
    with pytest.raises(FlightNotExposed):
        await draft_var(runtime, f"8a9999:{VOLCANO_ID}")


async def test_var_is_stored_audited_and_listed(runtime: FakeRuntime) -> None:
    doc = await draft_var(runtime, FLIGHT_ID, actor="desk:Ana K")

    listed = await list_docs(runtime.store, kind=DocKind.VAR)
    assert [item.id for item in listed] == [doc.id]
    assert await list_docs(runtime.store, kind=DocKind.SRA) == []
    [entry] = [
        item
        for item in await audit.list_entries(runtime.store)
        if item.action is AuditAction.DOC_DRAFTED
    ]
    assert entry.after is not None
    assert entry.after["flight_id"] == FLIGHT_ID


async def test_a_vars_encounter_counts_in_the_sras_reporting_section(
    runtime: FakeRuntime,
) -> None:
    runtime.exposed[FLIGHT_ID] = make_flight(inside=True)
    var = await draft_var(runtime, FLIGHT_ID)
    sra = await draft_sra(runtime, "java_bali")
    reporting = next(section for section in sra.sections if section.key == "reporting")

    assert reporting.fields[-1].value == "1 drafted, 0 signed"
    assert reporting.fields[-1].source_ids == [var.id]
    assert reporting.tables[0].rows == [[PROXY, "Semeru"]]


# --- sign-off ---------------------------------------------------------------------------


async def test_sign_off_fills_a_line_audits_and_completes_the_document(
    runtime: FakeRuntime,
) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)

    first = await sign_doc(
        runtime.store,
        runtime.bus,
        doc.id,
        role=SignRole.PILOT_IN_COMMAND,
        name="  Capt  Sari  ",
        actor="desk:Ana K",
    )
    assert first.status is DocStatus.DRAFT
    assert first.version == 2
    line = next(item for item in first.signatures if item.role is SignRole.PILOT_IN_COMMAND)
    assert (line.signed_name, line.signed_at, line.recorded_by) == (
        "Capt Sari",
        AT,
        "desk:Ana K",
    )

    second = await sign_doc(
        runtime.store,
        runtime.bus,
        doc.id,
        role=SignRole.DISPATCHER,
        name="Ana K",
        actor="desk:Ana K",
    )
    assert second.status is DocStatus.SIGNED
    assert second.version == 3
    assert second.header == VAR_HEADER  # a signature does not make it a transmitted report

    entries = [
        item
        for item in await audit.list_entries(runtime.store)
        if item.action is AuditAction.DOC_SIGNED
    ]
    assert [(e.after or {})["role"] for e in reversed(entries)] == [
        "PILOT_IN_COMMAND",
        "DISPATCHER",
    ]
    assert await audit.verify_chain(runtime.store) == []
    assert [event.data["status"] for event in runtime.bus.recent(SseEvent.DOC)][-1] == "SIGNED"
    assert await runtime.store.list_docs(Collection.OUTBOUND) == []  # nothing is queued


async def test_sign_off_refuses_a_repeat_a_foreign_role_and_a_bad_name(
    runtime: FakeRuntime,
) -> None:
    doc = await draft_var(runtime, FLIGHT_ID)
    sign = {"store": runtime.store, "bus": runtime.bus, "actor": "desk:Ana K"}
    await sign_doc(doc_id=doc.id, role=SignRole.DISPATCHER, name="Ana K", **sign)

    with pytest.raises(AlreadySigned):
        await sign_doc(doc_id=doc.id, role=SignRole.DISPATCHER, name="Ana K", **sign)
    with pytest.raises(InvalidSignature, match="no signature line"):
        await sign_doc(doc_id=doc.id, role=SignRole.SAFETY_MANAGER, name="Ana K", **sign)
    with pytest.raises(InvalidSignature, match="name"):
        await sign_doc(doc_id=doc.id, role=SignRole.PILOT_IN_COMMAND, name="A", **sign)
    with pytest.raises(DocNotFound):
        await sign_doc(doc_id="DOC-ffffffffffff", role=SignRole.DISPATCHER, name="Ana K", **sign)


# --- other work packages' documents -----------------------------------------------------


async def test_documents_of_another_kind_are_not_listed_or_returned(
    runtime: FakeRuntime,
) -> None:
    other = {"id": "DOC-0123456789ab", "kind": "HANDOVER", "created_at": "2026-10-09T19:00:00.000Z"}
    await runtime.store.put(Collection.DOCS, other["id"], other)
    sra = await draft_sra(runtime, "java_bali")

    assert [doc.id for doc in await list_docs(runtime.store)] == [sra.id]
    assert await get_doc(runtime.store, other["id"]) is None


# --- HTTP -------------------------------------------------------------------------------


class Harness:
    def __init__(self, tmp_path: Path, llm: ScriptedLlm) -> None:
        self.tmp_path = tmp_path
        self.llm = llm
        self.runtime: FakeRuntime | None = None

    async def factory(self, settings: Settings) -> Runtime:
        self.runtime = await make_runtime(self.tmp_path, self.llm)
        return cast(Runtime, self.runtime)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    harness = Harness(tmp_path, ScriptedLlm())
    app = create_app(make_settings(tmp_path), runtime_factory=harness.factory)
    app.include_router(router, prefix="/api")
    with TestClient(app) as test_client:
        yield test_client


def login(client: TestClient) -> None:
    response = client.post("/api/desk/login", json={"pin": PIN, "name": DISPATCHER})
    assert response.status_code == 200


def test_drafting_and_signing_need_a_desk_session(client: TestClient) -> None:
    assert client.post("/api/desk/docs/sra", json={"region": "java_bali"}).status_code == 401
    assert client.post("/api/desk/docs/var", json={"flight_id": FLIGHT_ID}).status_code == 401
    sign = {"name": "Ana K", "role": "DISPATCHER"}
    assert client.post("/api/desk/docs/DOC-0123456789ab/sign", json=sign).status_code == 401
    assert client.get("/api/docs").status_code == 200  # reading is public


def test_posts_need_the_csrf_guard(client: TestClient) -> None:
    login(client)
    response = client.post(
        "/api/desk/docs/sra",
        content=b'{"region": "java_bali"}',
        headers={"content-type": "text/plain"},
    )
    assert response.status_code == 403


def test_draft_list_read_and_sign_over_http(client: TestClient) -> None:
    login(client)
    sra = client.post("/api/desk/docs/sra", json={"region": "java_bali"})
    var = client.post("/api/desk/docs/var", json={"flight_id": FLIGHT_ID})
    assert sra.status_code == 200
    assert var.status_code == 200
    assert sra.json()["header"] == SRA_HEADER
    assert sra.json()["kind"] == "SRA"
    assert var.json()["kind"] == "VAR"

    listed = client.get("/api/docs").json()["docs"]
    assert {doc["kind"] for doc in listed} == {"SRA", "VAR"}
    assert [doc["id"] for doc in client.get("/api/docs?kind=VAR").json()["docs"]] == [
        var.json()["id"]
    ]
    assert client.get(f"/api/docs/{sra.json()['id']}").json()["region_key"] == "java_bali"

    signed = client.post(
        f"/api/desk/docs/{var.json()['id']}/sign",
        json={"name": "Capt Sari", "role": "PILOT_IN_COMMAND"},
    )
    assert signed.status_code == 200
    assert signed.json()["signatures"][0]["signed_name"] == "Capt Sari"
    again = client.post(
        f"/api/desk/docs/{var.json()['id']}/sign",
        json={"name": "Capt Sari", "role": "PILOT_IN_COMMAND"},
    )
    assert again.status_code == 409
    assert again.json()["error"] == "invalid_transition"
    foreign = client.post(
        f"/api/desk/docs/{var.json()['id']}/sign", json={"name": "Boss", "role": "SAFETY_MANAGER"}
    )
    assert foreign.status_code == 422
    assert foreign.json()["error"] == "validation_failed"


def test_http_errors_are_plain(client: TestClient) -> None:
    login(client)
    assert client.get("/api/docs/not-an-id").status_code == 404
    assert client.get("/api/docs/DOC-ffffffffffff").status_code == 404
    unknown = client.post("/api/desk/docs/sra", json={"region": "atlantis"})
    assert unknown.status_code == 404
    quiet = client.post("/api/desk/docs/sra", json={"region": "kyushu"})
    assert quiet.status_code == 409
    assert quiet.json()["error"] == "no_active_volcano"
    gone = client.post("/api/desk/docs/var", json={"flight_id": f"8a9999:{VOLCANO_ID}"})
    assert gone.status_code == 404
    assert client.post("/api/desk/docs/var", json={"flight_id": "nope"}).status_code == 422


def test_ai_unavailable_is_a_503(tmp_path: Path) -> None:
    llm = ScriptedLlm("gemini", [None])
    harness = Harness(tmp_path, llm)
    app = create_app(make_settings(tmp_path), runtime_factory=harness.factory)
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        login(client)
        response = client.post("/api/desk/docs/sra", json={"region": "java_bali"})
        assert response.status_code == 503
        assert response.json()["error"] == "ai_unavailable"
        assert response.json()["detail"].startswith("AI UNAVAILABLE: NO NARRATIVE RETURNED")
        assert client.get("/api/docs").json() == {"docs": []}


def test_the_region_keys_the_tests_use_exist() -> None:
    assert {"java_bali", "kyushu"} <= set(REGIONS)
    assert timeutil.now() == AT
