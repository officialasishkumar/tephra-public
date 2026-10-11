"""Crew and passenger messages and the shift handover brief.

No network and no live model: a counting stub and a scripted backend stand in for Gemini, the
SQLite store and desk state machines are the real ones.
"""

import json
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from pydantic import BaseModel
from test_api import DISPATCHER, FAILURE_ID, PIN, TASK_TOKEN, make_advisory, make_failure

from tephra.agents.llm import LlmCall, LlmPart, StubBackend, prompt_hash
from tephra.api.auth import CSRF_HEADER
from tephra.api.routes_comms import router
from tephra.api.server import create_app
from tephra.comms import handover, messages
from tephra.comms.models import (
    CrewPaxMessage,
    MessageKind,
    MessageStatus,
    RecoveryChange,
    RecoveryClosure,
    RecoveryInput,
)
from tephra.config import PROJECT_ROOT, Settings
from tephra.desk import approvals, audit
from tephra.feeds.airports import AirportCatalogue, load_airports
from tephra.models import (
    Advisory,
    AuditAction,
    Discrepancy,
    DiscrepancyKind,
    FeedHealth,
    FeedId,
    FeedStatus,
    GeoPolygon,
    LlmBackendName,
    OfficialLayer,
    OperatorPolicy,
    RunMode,
    Situation,
    SseEvent,
    TraceActor,
    TraceEvent,
    TraceStage,
    Volcano,
    polygon_from_latlon,
)
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.recovery.models import (
    Closure,
    FlightAction,
    RecoveryActionKind,
    RecoveryPlan,
    RecoveryScenario,
    SolveStatus,
)
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 12, 1, 0, tzinfo=UTC)
POLICY = load_policy(PROJECT_ROOT / "data")
AIRPORTS = load_airports(PROJECT_ROOT / "data", min_runway_m=POLICY.alternates.min_runway_m.value)
KNOWN_CODES = messages._known_codes(AIRPORTS)
ACTOR = "desk:Ana K"
RECOVERY_ID = "REC-0123456789ab"
SIGMET_ID = "SIGMET:WIII:1:20261012T0200Z"


@pytest.fixture(autouse=True)
def clock() -> Iterator[FixedClock]:
    with use_clock(FixedClock(AT)) as fixed:
        yield cast(FixedClock, fixed)


# --- stand-ins --------------------------------------------------------------------------


class CountingStub(StubBackend):
    """The offline stub, counting its calls."""

    def __init__(self) -> None:
        self.calls = 0

    async def structured[T: BaseModel](  # type: ignore[override]
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
        return await super().structured(
            tier="lite",
            system=system,
            parts=parts,
            schema=schema,
            stub=stub,
            temperature=temperature,
        )


class ScriptedLlm:
    """A fake 'gemini': answers from a script. A model is its answer, ``None`` an API error
    and a string an unreadable answer."""

    name: LlmBackendName = "gemini"

    def __init__(self, *answers: BaseModel | str | None) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    @property
    def calls(self) -> int:
        return len(self.prompts)

    def model_id(self, tier: str) -> str:
        return "gemini-test-lite"

    def reserve(self, tier: str) -> bool:
        return True

    def exhaust(self, tier: str) -> None:
        raise AssertionError("never closes a tier")

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
        self.prompts.append("\n".join(part.text or "" for part in parts))
        answer = self._answers.pop(0)
        value = answer if isinstance(answer, BaseModel) else None
        call = LlmCall(
            backend="gemini",
            model_id="gemini-test-lite",
            prompt_hash=prompt_hash(system, parts),
            raw_text=answer if isinstance(answer, str) else None,
            error="api_error 503 UNAVAILABLE" if answer is None else None,
        )
        return cast(T | None, value), call


@dataclass
class FakeRuntime:
    """The parts of ``tephra.pipeline.Runtime`` that messages and handover use."""

    store: Store
    llm: Any
    bus: EventBus = field(default_factory=EventBus)
    airports: AirportCatalogue = AIRPORTS
    policy: OperatorPolicy = POLICY
    mode: RunMode = RunMode.LIVE
    situations: dict[str, Situation] = field(default_factory=dict)
    traces: list[TraceEvent] = field(default_factory=list)

    def trace(
        self,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: str = "info",
        volcano_id: str | None = None,
        flight_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> TraceEvent:
        event = TraceEvent.new(stage, actor, message, level=level, detail=detail)  # type: ignore[arg-type]
        self.traces.append(event)
        return event


@pytest_asyncio.fixture
async def store(tmp_path: Path) -> AsyncIterator[Store]:
    settings = Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
    )
    opened = open_store(settings)
    yield opened
    await opened.aclose()


def recovery_plan(*, approved: bool = True) -> RecoveryInput:
    def at(hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 10, 12, hour, minute, tzinfo=UTC)

    return RecoveryInput(
        id=RECOVERY_ID,
        approved=approved,
        replay=False,
        changes=[
            RecoveryChange(
                flight_no="RFA101",
                origin_icao="WIII",
                dest_icao="WARR",
                std=at(3),
                kind="DELAY",
                delay_min=90,
                tail="PK-RFA1",
            ),
            RecoveryChange(
                flight_no="RFA102",
                origin_icao="WARR",
                dest_icao="WIII",
                std=at(6),
                kind="CANCEL",
                tail="PK-RFA1",
            ),
            RecoveryChange(
                flight_no="RFA103",
                origin_icao="WADD",
                dest_icao="WIII",
                std=at(5),
                kind="SWAP",
                tail="PK-RFA2",
                new_tail="PK-RFA3",
            ),
            RecoveryChange(
                flight_no="RFA201",
                origin_icao="RJFK",
                dest_icao="RJFF",
                std=at(5),
                kind="CANCEL",
                tail="PK-RFA4",
            ),
        ],
        closures=[
            RecoveryClosure(icao="WIII", start=at(2), end=at(8), source_ids=[SIGMET_ID]),
            RecoveryClosure(
                icao="RJFK", start=at(4), end=at(10), source_ids=["SIGMET:RJTD:2:20261012T0400Z"]
            ),
        ],
        input_hashes=["a" * 64],
    )


def plan_doc(
    plan: RecoveryInput, *, status: str = "APPROVED", chosen: bool = True
) -> dict[str, Any]:
    """The stored shape of a ``RecoveryPlan`` that holds ``plan``'s changes and closures."""
    closures = [
        Closure(
            icao=c.icao,
            start=c.start,
            end=c.end,
            reason="CLOSED BY TEST",
            source_ids=c.source_ids,
            open_ended=c.open_ended,
        )
        for c in plan.closures
    ]
    actions = [
        FlightAction(
            flight_no=c.flight_no,
            origin=c.origin_icao,
            dest=c.dest_icao,
            std=c.std,
            kind=RecoveryActionKind(c.kind),
            delay_min=c.delay_min,
            tail=c.tail,
            new_tail=c.new_tail,
            pax_booked=120,
        )
        for c in plan.changes
    ]
    keep = FlightAction(
        flight_no="RFA999",
        origin="WIII",
        dest="WARR",
        std=AT,
        kind=RecoveryActionKind.KEEP,
        tail="RFA-T09",
        pax_booked=100,
    )
    scenario = RecoveryScenario(
        id="SC-0123456789ab",
        label="Closure as forecast",
        extend_min=0,
        max_delay_min=360,
        status=SolveStatus.OPTIMAL,
        solver_status="OPTIMAL",
        solve_ms=5,
        actions=[*actions, keep],
        closures=closures,
    )
    stored = RecoveryPlan(
        id=plan.id,
        created_at=AT,
        replay=plan.replay,
        status=status,  # type: ignore[arg-type]
        closures=closures,
        scenarios=[scenario],
        chosen_scenario_id=scenario.id if chosen else None,
        llm_backend="stub",
        model_id="stub",
        prompt_hash="0" * 64,
        outcome="STUB",
    )
    return stored.model_dump(mode="json")


async def seed_plan(store: Store, plan: RecoveryInput, **kwargs: Any) -> None:
    await store.put(Collection.RECOVERY, plan.id, plan_doc(plan, **kwargs))


async def seed_recovery(store: Store, *, approved: bool = True) -> None:
    await seed_plan(store, recovery_plan(), status="APPROVED" if approved else "DRAFT")


async def seed_advisory(store: Store, advisory: Advisory) -> None:
    created = await store.compare_and_set_advisory(advisory.id, 0, advisory.model_dump(mode="json"))
    assert created


def approved_advisory() -> Advisory:
    return make_advisory().model_copy(
        update={
            "id": "adv_aaaaaaaaaaaa",
            "flight_id": "8a0999:263300",
            "hex": "8a0999",
            "proxy_flight": "RFA4821",
        }
    )


async def runtime_for(store: Store, llm: Any | None = None) -> FakeRuntime:
    return FakeRuntime(store=store, llm=llm or CountingStub())


async def messages_in(store: Store) -> list[CrewPaxMessage]:
    return await messages.list_messages(store, limit=100, status=None)


def body_of(message: CrewPaxMessage, language: str) -> str:
    return message.final_bodies[language]  # type: ignore[index]


# --- route facts ------------------------------------------------------------------------


def test_languages_follow_the_route() -> None:
    def langs(a: str, b: str) -> list[str]:
        return messages.languages_for(AIRPORTS.get(a), AIRPORTS.get(b))  # type: ignore[arg-type]

    assert langs("WIII", "WARR") == ["id", "en"]
    assert langs("RJFK", "RJFF") == ["ja", "en"]
    assert langs("WIII", "RJFF") == ["id", "ja", "en"]
    assert langs("RPLL", "RPVM") == ["en"]


@pytest.mark.parametrize(
    ("icao", "expected"),
    [
        ("WIII", "2026-10-12 08:00 WIB"),
        ("WADD", "2026-10-12 09:00 WITA"),
        ("WAPP", "2026-10-12 10:00 WIT"),
        ("RJFK", "2026-10-12 10:00 JST"),
        ("YPDN", "2026-10-12 01:00 UTC"),
    ],
)
def test_local_time_names_the_zone(icao: str, expected: str) -> None:
    airport = AIRPORTS.get(icao)
    assert airport is not None
    assert messages.local_text(AT, airport) == expected


# --- the template validator -------------------------------------------------------------


def spec_of(kind: str = "pax") -> messages.TemplateSpec:
    if kind == "pax":
        return messages.passenger_spec("CANCELLED", messages.Jurisdiction.ID, ("id", "en"))
    if kind == "crew":
        return messages.crew_notice_spec(("en",))
    return messages.crew_briefing_spec()


def templates(spec: messages.TemplateSpec, **texts: str) -> messages.TemplateSet:
    stub = messages.stub_templates(spec)
    by_language = {text.language: text.text for text in stub.texts} | texts
    return messages.TemplateSet(
        texts=[
            messages.TemplateText(language=lang, text=by_language[lang]) for lang in spec.languages
        ]
    )


def problems_for(spec: messages.TemplateSpec, **texts: str) -> list[str]:
    return messages.template_problems(templates(spec, **texts), spec, known_codes=KNOWN_CODES)


@pytest.mark.parametrize(
    "spec",
    [
        messages.passenger_spec(status, jurisdiction, languages)
        for status in ("CANCELLED", "DELAYED")
        for jurisdiction, languages in (
            (messages.Jurisdiction.ID, ("id", "en")),
            (messages.Jurisdiction.JP, ("ja", "en")),
            (messages.Jurisdiction.OTHER, ("en",)),
        )
    ]
    + [messages.crew_notice_spec(("id", "ja", "en")), messages.crew_briefing_spec()],
)
def test_the_stub_templates_pass_the_checks(spec: messages.TemplateSpec) -> None:
    assert problems_for(spec) == []


def test_a_digit_outside_a_placeholder_is_rejected() -> None:
    spec = spec_of()
    stub_en = templates(spec).texts[1].text
    for bad in (
        stub_en + " Call 0804 1 807.",
        stub_en.replace("{FLIGHT}", "RFA101"),
        stub_en + " Refund in \uff13\uff10 days.",
    ):
        found = problems_for(spec, en=bad)
        assert any("DIGITS OUTSIDE PLACEHOLDERS" in problem for problem in found), bad


def test_a_missing_or_unknown_placeholder_is_rejected() -> None:
    spec = spec_of()
    stub_id = templates(spec).texts[0].text
    missing = problems_for(spec, id=stub_id.replace("{CONTACT}", "kami"))
    assert any("MISSING REQUIRED PLACEHOLDERS: CONTACT" in problem for problem in missing)
    unknown = problems_for(spec, id=stub_id + " {GATE}")
    assert any("UNKNOWN PLACEHOLDERS: GATE" in problem for problem in unknown)
    malformed = problems_for(spec, id=stub_id + " {contact}")
    assert any("MALFORMED PLACEHOLDER" in problem for problem in malformed)


def test_addresses_and_airport_codes_are_rejected() -> None:
    spec = spec_of()
    stub_en = templates(spec).texts[1].text
    assert any(
        "WEB ADDRESSES" in p for p in problems_for(spec, en=stub_en + " See www.rfa.example")
    )
    assert any(
        "WEB ADDRESSES" in p for p in problems_for(spec, en=stub_en + " Mail ops@rfa.example")
    )
    assert any("AIRPORT CODES (CGK)" in p for p in problems_for(spec, en=stub_en + " Go to CGK."))
    assert any(
        "AIRPORT CODES (WIII)" in p for p in problems_for(spec, en=stub_en + " WIII is shut.")
    )


def test_the_language_and_script_must_match() -> None:
    spec = messages.passenger_spec("CANCELLED", messages.Jurisdiction.JP, ("ja", "en"))
    stub = templates(spec)
    swapped = problems_for(spec, ja=stub.texts[1].text, en=stub.texts[0].text)
    assert any(problem.startswith("JA: TEXT IS NOT JAPANESE") for problem in swapped)
    assert any(problem.startswith("EN: TEXT MUST NOT CONTAIN JAPANESE") for problem in swapped)


def test_the_answer_needs_exactly_the_requested_languages() -> None:
    spec = spec_of()
    only_one = messages.TemplateSet(texts=templates(spec).texts[:1])
    found = messages.template_problems(only_one, spec, known_codes=KNOWN_CODES)
    assert found == ["ANSWER MUST HAVE EXACTLY ONE TEXT PER LANGUAGE: id, en"]


def test_the_model_is_given_placeholder_names_and_meanings_never_values() -> None:
    facts = messages._facts(spec_of())
    assert set(facts["required_placeholders"]) == set(spec_of().required)
    assert facts["languages"] == ["id", "en"]
    assert "RFA101" not in json.dumps(facts)


def test_the_prompt_names_the_placeholders_the_specs_use() -> None:
    prompt = messages.PROMPT_PATH.read_text(encoding="utf-8")
    for spec in (spec_of(), spec_of("crew"), spec_of("briefing")):
        for name in spec.required:
            assert f"{{{name}}}" in prompt or name in {"TAIL"} or name in prompt, name


# --- drafting from a recovery plan ------------------------------------------------------


async def test_a_recovery_plan_gives_passenger_and_crew_drafts(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store)
    drafted = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)

    by_flight = {m.flight_no: m for m in drafted if m.kind is MessageKind.PASSENGER_NOTICE}
    assert set(by_flight) == {"RFA101", "RFA102", "RFA201"}  # the swap has no passenger notice
    tails = {m.tail for m in drafted if m.kind is MessageKind.CREW_NOTICE}
    assert tails == {"PK-RFA1", "PK-RFA2", "PK-RFA3", "PK-RFA4"}
    assert all(m.status is MessageStatus.DRAFT and m.version == 1 for m in drafted)
    assert all(m.llm_backend == "stub" and m.source_id == RECOVERY_ID for m in drafted)
    assert runtime.llm.calls == 5  # 3 passenger groups + 2 crew language sets, not 7


def test_a_delay_shorter_than_the_policy_minimum_gets_no_passenger_notice() -> None:
    minimum = POLICY.recovery.pax_notice_min_delay_min.value
    assert minimum == 30
    plan = recovery_plan()
    plan = plan.model_copy(
        update={
            "changes": [
                c.model_copy(update={"delay_min": minimum - 1}) if c.kind == "DELAY" else c
                for c in plan.changes
            ]
        }
    )
    flights = {t.flight_no for t in messages.passenger_targets(plan, AIRPORTS, POLICY)}
    assert "RFA101" not in flights  # the delay is one minute under the minimum
    assert "RFA102" in flights  # a cancellation always gets a notice

    at_minimum = plan.model_copy(
        update={
            "changes": [
                c.model_copy(update={"delay_min": minimum}) if c.kind == "DELAY" else c
                for c in plan.changes
            ]
        }
    )
    assert "RFA101" in {
        t.flight_no for t in messages.passenger_targets(at_minimum, AIRPORTS, POLICY)
    }

    stricter = POLICY.model_copy(
        update={
            "recovery": POLICY.recovery.model_copy(
                update={
                    "pax_notice_min_delay_min": POLICY.recovery.pax_notice_min_delay_min.model_copy(
                        update={"value": minimum + 100}
                    )
                }
            )
        }
    )
    assert "RFA101" not in {
        t.flight_no for t in messages.passenger_targets(plan, AIRPORTS, stricter)
    }


async def test_a_delay_notice_is_filled_by_code_in_both_languages(store: Store) -> None:
    await seed_recovery(store)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    delay = next(m for m in drafted if m.flight_no == "RFA101")
    assert [text.language for text in delay.texts] == ["id", "en"]
    for language in ("id", "en"):
        body = body_of(delay, language)
        assert "{" not in body
        assert "RFA101" in body
        assert "2026-10-12 10:00 WIB" in body  # the 03:00Z departure
        assert "2026-10-12 11:30 WIB" in body  # 90 minutes later
        assert "90" in body
        assert SIGMET_ID in body
        assert "30" in body  # card refunds, PM 89 Pasal 10
    assert "Penerbangan RFA101" in body_of(delay, "id")
    assert "PM 89 Tahun 2015 Pasal 6 ayat (2)" in body_of(delay, "id")
    assert "PM 89/2015 Article 6(2)" in body_of(delay, "en")
    assert "Soekarno-Hatta International Airport (CGK)" in body_of(delay, "en")


async def test_a_cancellation_names_the_closure_end_as_the_next_update(store: Store) -> None:
    await seed_recovery(store)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    cancelled = next(m for m in drafted if m.flight_no == "RFA102")
    assert "2026-10-12 15:00 WIB" in body_of(cancelled, "en")  # the closure ends 08:00Z
    assert "cancelled" in body_of(cancelled, "en")
    assert "dibatalkan" in body_of(cancelled, "id")


async def test_a_japanese_route_gets_japanese_and_english(store: Store) -> None:
    await seed_recovery(store)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    japan = next(m for m in drafted if m.flight_no == "RFA201")
    assert [text.language for text in japan.texts] == ["ja", "en"]
    assert "欠航" in body_of(japan, "ja")
    assert "2026-10-12 19:00 JST" in body_of(japan, "ja")  # the closure ends 10:00Z
    assert "Fukuoka Airport (FUK)" in body_of(japan, "en")
    assert "カレンダー日" not in body_of(japan, "ja")  # no PM 89 card rule outside Indonesia
    assert "conditions of carriage" in body_of(japan, "en")


async def test_a_crew_notice_lists_every_change_of_the_aircraft(store: Store) -> None:
    await seed_recovery(store)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    crew = {m.tail: m for m in drafted if m.kind is MessageKind.CREW_NOTICE}
    body = body_of(crew["PK-RFA1"], "en")
    assert "RFA101" in body
    assert "DELAYED 90 MIN" in body
    assert "RFA102" in body
    assert "CANCELLED" in body
    assert "MOVES TO AIRCRAFT PK-RFA3" in body_of(crew["PK-RFA2"], "en")
    assert "PK-RFA3" in body_of(crew["PK-RFA3"], "en")
    assert [text.language for text in crew["PK-RFA4"].texts] == ["ja", "en"]


async def test_drafting_again_makes_no_call_and_no_duplicate(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store)
    first = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    calls = runtime.llm.calls
    again = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert runtime.llm.calls == calls
    assert [m.id for m in again] == [m.id for m in first]
    assert len(await messages_in(store)) == len(first)


async def test_a_rejected_message_can_be_drafted_again(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store)
    first = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    victim = first[0]
    await messages.reject(
        store, runtime.bus, victim.id, expected_version=1, reason="wrong tone", actor=ACTOR
    )
    again = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    redrafted = next(m for m in again if m.dedupe_key == victim.dedupe_key)
    assert redrafted.id != victim.id
    assert redrafted.status is MessageStatus.DRAFT


async def test_drafting_audits_each_draft_and_publishes_it(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store)
    async with runtime.bus.subscribe() as events:
        drafted = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
        published = [await events.get(0.1) for _ in drafted]
    assert {event.name for event in published if event} == {SseEvent.MESSAGE.value}
    entries = [
        e for e in await audit.list_entries(store) if e.action is AuditAction.MESSAGE_DRAFTED
    ]
    assert len(entries) == len(drafted)
    assert all(entry.actor == ACTOR for entry in entries)
    assert await audit.verify_chain(store) == []
    assert any("NO MODEL" in event.message for event in runtime.traces)


async def test_a_plan_that_is_not_approved_or_missing_is_refused(store: Store) -> None:
    runtime = await runtime_for(store)
    with pytest.raises(messages.SourceNotFound):
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    await seed_recovery(store, approved=False)
    with pytest.raises(messages.SourceNotApproved):
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert runtime.llm.calls == 0


async def test_a_plan_without_a_chosen_scenario_is_unusable(store: Store) -> None:
    await seed_plan(store, recovery_plan(), chosen=False)
    runtime = await runtime_for(store)
    with pytest.raises(messages.SourceUnusable, match="no chosen scenario"):
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)


async def test_only_the_changed_flights_get_messages(store: Store) -> None:
    await seed_recovery(store)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    assert "RFA999" not in {m.flight_no for m in drafted}  # a KEEP flight


async def test_an_open_ended_closure_gives_no_invented_end_or_update_time(store: Store) -> None:
    plan = recovery_plan()
    plan.closures[0] = plan.closures[0].model_copy(update={"open_ended": True})
    await seed_plan(store, plan)
    drafted = await messages.draft_messages(
        await runtime_for(store), recovery_id=RECOVERY_ID, actor=ACTOR
    )
    cancelled = next(m for m in drafted if m.flight_no == "RFA102")
    body = body_of(cancelled, "en")
    assert "end not yet published" in body
    assert "Next update by the time the end of the closure is published" in body
    assert "2026-10-12 15:00" not in body  # the planning horizon is not an end
    assert "waktu berakhir belum diumumkan" in body_of(cancelled, "id")


async def test_a_plan_with_no_closure_cannot_state_a_reason(store: Store) -> None:
    await seed_plan(store, recovery_plan().model_copy(update={"closures": []}))
    runtime = await runtime_for(store)
    with pytest.raises(messages.SourceUnusable):
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert await messages_in(store) == []


# --- drafting from an advisory ----------------------------------------------------------


async def test_an_approved_advisory_gives_an_english_crew_briefing(store: Store) -> None:
    advisory = approved_advisory()
    await seed_advisory(store, advisory)
    runtime = await runtime_for(store)
    bus = runtime.bus
    await approvals.approve(store, bus, advisory.id, expected_version=1, actor=ACTOR)
    (briefing,) = await messages.draft_messages(runtime, advisory_id=advisory.id, actor=ACTOR)
    assert briefing.kind is MessageKind.CREW_BRIEFING
    assert [text.language for text in briefing.texts] == ["en"]
    body = body_of(briefing, "en")
    assert "GIA417" in body
    assert "SEMERU" in body
    assert "HOLD FL350" in body
    assert "ENTRY IN 14 MIN" in body
    assert "ICAO DOC 9974" in body
    assert "VERIFY EVERY PROCEDURE AGAINST THE OPERATOR QRH" in body
    assert "VAR, AML ENTRY" in body
    assert briefing.source_version == 2  # the approved version


async def test_a_draft_advisory_is_not_briefed(store: Store) -> None:
    await seed_advisory(store, approved_advisory())
    with pytest.raises(messages.SourceNotApproved):
        await messages.draft_messages(
            await runtime_for(store), advisory_id="adv_aaaaaaaaaaaa", actor=ACTOR
        )


# --- the model may fail, and nothing is substituted ------------------------------------


async def test_a_model_error_stores_nothing_and_says_ai_unavailable(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store, ScriptedLlm(None))
    with pytest.raises(messages.AiUnavailable) as raised:
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert str(raised.value).startswith("AI UNAVAILABLE: NO ANSWER RETURNED (api_error 503")
    assert await messages_in(store) == []
    failed = [e for e in await audit.list_entries(store) if e.action is AuditAction.AI_FAILED]
    assert len(failed) == 1
    assert (failed[0].note or "").startswith("AI UNAVAILABLE")
    assert any(e.level == "error" and "AI UNAVAILABLE" in e.message for e in runtime.traces)


async def test_a_template_failing_the_checks_gets_one_repair(store: Store) -> None:
    await seed_recovery(store)
    spec = messages.passenger_spec("DELAYED", messages.Jurisdiction.ID, ("id", "en"))
    bad = templates(spec, en=templates(spec).texts[1].text + " It lasts 3 hours.")
    llm = ScriptedLlm(bad, templates(spec))
    runtime = await runtime_for(store, llm)
    await seed_plan(
        store, recovery_plan().model_copy(update={"changes": [recovery_plan().changes[0]]})
    )
    # The crew notice needs its own template: script it too.
    crew = messages.crew_notice_spec(("id", "en"))
    llm._answers.append(templates(crew))
    drafted = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert llm.calls == 3
    assert "DIGITS OUTSIDE PLACEHOLDERS" in llm.prompts[1]  # the repair prompt lists the problem
    assert {m.kind for m in drafted} == {MessageKind.PASSENGER_NOTICE, MessageKind.CREW_NOTICE}
    assert all(m.llm_backend == "gemini" for m in drafted)
    assert any("AI-WRITTEN" in event.message for event in runtime.traces)


async def test_a_template_still_failing_after_the_repair_is_ai_unavailable(store: Store) -> None:
    await seed_recovery(store)
    spec = messages.passenger_spec("DELAYED", messages.Jurisdiction.ID, ("id", "en"))
    bad = templates(spec, en=templates(spec).texts[1].text + " 3 hours.")
    runtime = await runtime_for(store, ScriptedLlm(bad, bad))
    with pytest.raises(messages.AiUnavailable) as raised:
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert "FAILED CHECKS AFTER REPAIR" in str(raised.value)
    assert runtime.llm.calls == 2
    assert await messages_in(store) == []


async def test_an_unreadable_answer_is_repaired_once_then_fails(store: Store) -> None:
    await seed_recovery(store)
    runtime = await runtime_for(store, ScriptedLlm("not json", None))
    with pytest.raises(messages.AiUnavailable):
        await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    assert runtime.llm.calls == 2


# --- dispatcher decisions ---------------------------------------------------------------


async def draft_one(store: Store) -> tuple[FakeRuntime, CrewPaxMessage]:
    await seed_recovery(store)
    runtime = await runtime_for(store)
    drafted = await messages.draft_messages(runtime, recovery_id=RECOVERY_ID, actor=ACTOR)
    return runtime, next(m for m in drafted if m.flight_no == "RFA101")


async def test_approval_queues_the_message_on_the_outbound_collection(store: Store) -> None:
    runtime, draft = await draft_one(store)
    decided = await messages.approve(
        store, runtime.bus, draft.id, expected_version=1, actor="desk:Bo L"
    )
    assert decided.status is MessageStatus.APPROVED
    assert decided.version == 2
    assert decided.decided_by == "desk:Bo L"
    (doc,) = await store.list_docs(Collection.OUTBOUND)
    assert doc["destination"] == "tephra-outbound"
    assert doc["advisory_id"] == draft.id
    assert doc["status"] == "APPROVED"
    assert doc["proxy_flight"] == "RFA101"
    assert "[ID]" in doc["text"]
    assert "[EN]" in doc["text"]
    assert "NOT FOR OPERATIONAL USE" in doc["text"]
    assert f"MESSAGE {draft.id} VERSION 2 APPROVED BY desk:Bo L" in doc["text"]
    actions = [e.action for e in await audit.list_entries(store)]
    assert AuditAction.MESSAGE_DECIDED in actions
    assert AuditAction.OUTBOUND_QUEUED in actions
    assert await audit.verify_chain(store) == []


async def test_an_edit_replaces_only_the_named_language(store: Store) -> None:
    runtime, draft = await draft_one(store)
    decided = await messages.edit_and_approve(
        store,
        runtime.bus,
        draft.id,
        expected_version=1,
        bodies={"en": "  Flight RFA101 now leaves later.  "},
        actor=ACTOR,
    )
    assert decided.status is MessageStatus.EDITED
    assert body_of(decided, "en") == "Flight RFA101 now leaves later."
    assert body_of(decided, "id") == draft.texts[0].body
    assert decided.texts[1].body == draft.texts[1].body  # the original draft text is kept
    (doc,) = await store.list_docs(Collection.OUTBOUND)
    assert doc["status"] == "EDITED"
    assert "Flight RFA101 now leaves later." in doc["text"]


@pytest.mark.parametrize(
    ("bodies", "needle"),
    [({"ja": "x"}, "no such language"), ({"en": "   "}, "empty"), ({"en": "x" * 3001}, "longer")],
)
async def test_a_bad_edit_is_rejected(store: Store, bodies: dict[str, str], needle: str) -> None:
    runtime, draft = await draft_one(store)
    with pytest.raises(messages.EditRejected) as raised:
        await messages.edit_and_approve(
            store,
            runtime.bus,
            draft.id,
            expected_version=1,
            bodies=bodies,
            actor=ACTOR,  # type: ignore[arg-type]
        )
    assert needle in raised.value.problems[0]
    assert (await messages.get_message(store, draft.id)).status is MessageStatus.DRAFT  # type: ignore[union-attr]


async def test_reject_needs_a_reason_and_queues_nothing(store: Store) -> None:
    runtime, draft = await draft_one(store)
    with pytest.raises(messages.EditRejected):
        await messages.reject(
            store, runtime.bus, draft.id, expected_version=1, reason=" a ", actor=ACTOR
        )
    rejected = await messages.reject(
        store, runtime.bus, draft.id, expected_version=1, reason="Wrong reason", actor=ACTOR
    )
    assert rejected.status is MessageStatus.REJECTED
    assert rejected.reject_reason == "Wrong reason"
    assert await store.list_docs(Collection.OUTBOUND) == []


async def test_a_stale_version_conflicts_and_a_decided_message_never_moves(store: Store) -> None:
    runtime, draft = await draft_one(store)
    with pytest.raises(messages.VersionConflict) as conflict:
        await messages.approve(store, runtime.bus, draft.id, expected_version=7, actor=ACTOR)
    assert conflict.value.current.version == 1
    await messages.approve(store, runtime.bus, draft.id, expected_version=1, actor=ACTOR)
    with pytest.raises(messages.InvalidTransition):
        await messages.approve(store, runtime.bus, draft.id, expected_version=2, actor=ACTOR)
    with pytest.raises(messages.MessageNotFound):
        await messages.approve(
            store, runtime.bus, "msg_000000000000", expected_version=1, actor=ACTOR
        )
    assert len(await store.list_docs(Collection.OUTBOUND)) == 1


async def test_two_dispatchers_cannot_both_decide(store: Store) -> None:
    import asyncio

    runtime, draft = await draft_one(store)
    results = await asyncio.gather(
        messages.approve(store, runtime.bus, draft.id, expected_version=1, actor="desk:A"),
        messages.approve(store, runtime.bus, draft.id, expected_version=1, actor="desk:B"),
        return_exceptions=True,
    )
    assert sum(isinstance(r, CrewPaxMessage) for r in results) == 1
    assert sum(isinstance(r, messages.VersionConflict) for r in results) == 1
    assert len(await store.list_docs(Collection.OUTBOUND)) == 1


async def test_list_messages_filters_by_status_and_mode(store: Store) -> None:
    runtime, draft = await draft_one(store)
    await messages.approve(store, runtime.bus, draft.id, expected_version=1, actor=ACTOR)
    drafts = await messages.list_messages(store, status=MessageStatus.DRAFT, replay=False)
    approved = await messages.list_messages(store, status=MessageStatus.APPROVED)
    assert draft.id not in {m.id for m in drafts}
    assert [m.id for m in approved] == [draft.id]
    assert await messages.list_messages(store, replay=True) == []


# --- handover ---------------------------------------------------------------------------

SINCE = AT - timedelta(hours=8)


def official_layer() -> OfficialLayer:
    ring = polygon_from_latlon([(-8.0, 112.0), (-8.0, 113.0), (-7.0, 113.0), (-7.0, 112.0)])
    assert isinstance(ring, GeoPolygon)
    return OfficialLayer(
        source_id="SIGMET:WARR:5:20261011T2300Z",
        kind="SIGMET",
        layer="SIGMET",
        label="SIGMET WARR 5",
        polygon=ring,
        base_ft=0,
        top_ft=15000,
        valid_from=AT - timedelta(hours=2),
        valid_to=AT + timedelta(hours=4),
    )


def situation() -> Situation:
    volcano = Volcano(
        id="263300",
        name="Semeru",
        country="Indonesia",
        lat=-8.1,
        lon=112.9,
        summit_elev_m=3676,
        observatory="PVMBG",
        vaac="DARWIN",  # type: ignore[arg-type]
    )
    return Situation(
        volcano=volcano,
        as_of=AT,
        mode=RunMode.LIVE,
        active_reasons=["SIGMET"],
        official_layers=[official_layer()],
        discrepancies=[
            Discrepancy(
                id="D-1a2b3c4d",
                volcano_id="263300",
                kind=DiscrepancyKind.HEIGHT_MISMATCH,
                aspect="top",
                source_ids=["SIGMET:WARR:5:20261011T2300Z", "VONA:SMR:20261011T2200Z"],
                values={"a": "FL150", "b": "FL200"},
                summary="SIGMET top FL150 but VONA says FL200",
            )
        ],
    )


async def seed_shift(store: Store) -> Advisory:
    """One open advisory, one decided advisory, one AI failure and one stale feed."""
    open_one = make_advisory()
    decided = approved_advisory()
    await seed_advisory(store, open_one)
    await seed_advisory(store, decided)
    await approvals.approve(store, EventBus(), decided.id, expected_version=1, actor="desk:Bo L")
    await store.put(Collection.AI_FAILURES, FAILURE_ID, make_failure().model_dump(mode="json"))
    await store.put_feed_state(
        FeedHealth(
            feed=FeedId.SIGMET,
            status=FeedStatus.STALE,
            cadence_s=60,
            last_success_at=AT - timedelta(hours=1),
        )
    )
    return open_one


async def test_the_brief_is_gathered_by_code(store: Store) -> None:
    await seed_shift(store)
    runtime = await runtime_for(store)
    runtime.situations["263300"] = situation()
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")

    assert brief.severity == "critical"  # an unplanned flight is open
    assert brief.incoming == "Bo L"
    assert brief.shift_from == SINCE
    assert brief.shift_to == AT
    assert brief.llm_backend == "stub"
    assert [a.source_id for a in brief.weather_ash.official_areas] == [
        "SIGMET:WARR:5:20261011T2300Z"
    ]
    assert brief.weather_ash.disagreements[0].text == "SIGMET top FL150 but VONA says FL200"
    assert brief.equipment_data.feeds_stale[0].startswith("sigmet STALE (last good 120000Z)")
    rows = {row.flight: row for row in brief.traffic}
    assert rows["RFA4821"].status == "approved"
    assert rows["RFA4821"].plan == "HOLD FL350"
    assert any(row.plan == "NO AI PLAN" for row in brief.traffic)
    owners = {action.owner for action in brief.actions_open}
    assert owners == {"Bo L"}
    decide = next(a for a in brief.actions_open if a.source_ids == [make_advisory().id])
    assert decide.due_utc == make_advisory().created_at + timedelta(minutes=14)
    assert [d.by for d in brief.decisions_made] == ["desk:Bo L"]
    assert "approved" in brief.decisions_made[0].what
    assert brief.receiver_ack.read_back_by is None
    assert FAILURE_ID in brief.evidence_ids


async def test_the_brief_is_stored_audited_and_published(store: Store) -> None:
    await seed_shift(store)
    runtime = await runtime_for(store)
    async with runtime.bus.subscribe() as events:
        brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
        event = await events.get(0.1)
    assert event is not None
    assert event.name == SseEvent.DOC.value
    stored = await handover.get_handover(store, brief.id)
    assert stored == brief
    drafted = [e for e in await audit.list_entries(store) if e.action is AuditAction.DOC_DRAFTED]
    assert drafted[0].actor == "desk:Ana K"
    assert (drafted[0].after or {})["handover_id"] == brief.id
    assert await handover.get_handover(store, "ho_000000000000") is None


@pytest.mark.parametrize(
    ("seeding", "expected"),
    [("nothing", "calm"), ("area", "watch"), ("draft", "active"), ("failure", "critical")],
)
async def test_severity_is_set_by_code(store: Store, seeding: str, expected: str) -> None:
    runtime = await runtime_for(store)
    if seeding == "area":
        runtime.situations["263300"] = situation()
    if seeding == "draft":
        await seed_advisory(store, make_advisory())
    if seeding == "failure":
        await store.put(Collection.AI_FAILURES, FAILURE_ID, make_failure().model_dump(mode="json"))
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert brief.severity == expected


async def test_a_draft_for_a_flight_inside_the_hazard_is_critical(store: Store) -> None:
    await seed_advisory(store, make_advisory().model_copy(update={"inside_now": True}))
    runtime = await runtime_for(store)
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert brief.severity == "critical"
    assert brief.actions_open[0].due_utc is None


def narrative(**fields: Any) -> handover.Narrative:
    base: dict[str, Any] = {
        "situation": "SIGMET WARR 5 is valid until 120500Z and one flight awaits a decision.",
        "situation_source_ids": ["SIGMET:WARR:5:20261011T2300Z"],
        "contingencies": [],
    }
    return handover.Narrative.model_validate(base | fields)


FACTS = "SIGMET WARR 5 valid 112300Z to 120500Z from FL000 to FL150"
IDS = {"SIGMET:WARR:5:20261011T2300Z"}


def narrative_problems(model: handover.Narrative) -> list[str]:
    return handover.narrative_problems(model, facts_text=FACTS, evidence_ids=IDS)


def test_a_narrative_copying_the_evidence_passes() -> None:
    assert narrative_problems(narrative()) == []


@pytest.mark.parametrize(
    ("change", "needle"),
    [
        ({"situation": "The ash top is FL200."}, "NUMBERS OR TIMES NOT IN THE EVIDENCE: 200"),
        ({"situation": "SIGMET WARR 5 ends 18:00."}, "18:00"),
        ({"situation_source_ids": ["SIGMET:XXXX:1"]}, "CITES IDS NOT IN THE EVIDENCE"),
        ({"situation_source_ids": []}, "SITUATION CITES NO SOURCE ID"),
        ({"situation": " "}, "SITUATION IS EMPTY"),
        ({"situation": "x" * 901}, "LONGER THAN 900"),
    ],
)
def test_a_bad_narrative_is_rejected(change: dict[str, Any], needle: str) -> None:
    found = narrative_problems(narrative(**change))
    assert any(needle in problem for problem in found), found


def test_contingencies_are_checked_like_the_situation() -> None:
    line = {"condition": "If the flight enters at 1930Z", "then": "ask the desk", "source_ids": []}
    found = narrative_problems(narrative(contingencies=[line]))
    assert any("CONTINGENCY 1 CITES NO SOURCE ID" in problem for problem in found)
    assert any("1930" in problem for problem in found)
    many = [dict(line, source_ids=list(IDS), condition="If asked") for _ in range(6)]
    assert any("MORE THAN 5" in p for p in narrative_problems(narrative(contingencies=many)))


async def test_the_model_writes_only_the_narrative(store: Store) -> None:
    await seed_shift(store)
    llm = ScriptedLlm(
        narrative(
            situation="One advisory is approved and one flight has no AI plan.",
            situation_source_ids=[FAILURE_ID],
            contingencies=[
                {
                    "condition": "If the unplanned flight is not handled",
                    "then": "brief the desk",
                    "source_ids": [FAILURE_ID],
                }
            ],
        )
    )
    runtime = await runtime_for(store, llm)
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert brief.llm_backend == "gemini"
    assert brief.situation.source_ids == [FAILURE_ID]
    assert brief.contingencies[0].then == "brief the desk"
    assert "desk:" not in llm.prompts[0]  # no dispatcher name reaches the model
    assert "Bo L" not in llm.prompts[0]
    assert "Ana K" not in llm.prompts[0]
    assert any("AI-WRITTEN" in event.message for event in runtime.traces)


async def test_a_failed_narrative_gives_no_brief(store: Store) -> None:
    await seed_shift(store)
    invented = narrative(situation="Nine flights are held.")
    runtime = await runtime_for(store, ScriptedLlm(invented, invented))
    with pytest.raises(messages.AiUnavailable) as raised:
        await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert "NARRATIVE FAILED CHECKS AFTER REPAIR" in str(raised.value)
    assert await store.list_docs(Collection.DOCS) == []
    assert any(e.action is AuditAction.AI_FAILED for e in await audit.list_entries(store))

    runtime = await runtime_for(store, ScriptedLlm(None))
    with pytest.raises(messages.AiUnavailable):
        await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert await store.list_docs(Collection.DOCS) == []


async def test_the_read_back_is_allowed_with_open_drafts_and_records_them(store: Store) -> None:
    open_one = await seed_shift(store)
    runtime = await runtime_for(store)
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    assert brief.handed_over_open == [open_one.id]
    assert all(
        action.action.startswith(handover.HANDED_OVER_OPEN)
        for action in brief.actions_open
        if open_one.id in action.source_ids
    )
    acked = await handover.acknowledge(runtime, brief.id, actor="desk:Bo L")
    assert acked.receiver_ack.read_back_by == "desk:Bo L"
    assert acked.receiver_ack.utc == AT
    assert acked.receiver_ack.open_drafts == [open_one.id]
    stored = await handover.get_handover(store, brief.id)
    assert stored is not None
    assert stored.receiver_ack.open_drafts == [open_one.id]
    entries = [e for e in await audit.list_entries(store) if e.action is AuditAction.HANDOVER_ACKED]
    assert len(entries) == 1
    assert entries[0].after is not None
    assert entries[0].after["handed_over_open"] == [open_one.id]


async def test_a_decided_draft_is_not_recorded_as_open_at_the_read_back(store: Store) -> None:
    open_one = await seed_shift(store)
    runtime = await runtime_for(store)
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    await approvals.approve(store, runtime.bus, open_one.id, expected_version=1, actor="desk:Bo L")
    acked = await handover.acknowledge(runtime, brief.id, actor="desk:Bo L")
    assert brief.handed_over_open == [open_one.id]
    assert acked.receiver_ack.open_drafts == []


async def test_a_second_read_back_keeps_the_first(store: Store) -> None:
    runtime = await runtime_for(store)
    brief = await handover.draft_handover(runtime, SINCE, "Ana K", "Bo L")
    first = await handover.acknowledge(runtime, brief.id, actor="desk:Bo L")
    second = await handover.acknowledge(runtime, brief.id, actor="desk:Cy M")
    assert second.receiver_ack == first.receiver_ack
    entries = [e for e in await audit.list_entries(store) if e.action is AuditAction.HANDOVER_ACKED]
    assert len(entries) == 1


async def test_a_missing_handover_cannot_be_read_back(store: Store) -> None:
    with pytest.raises(handover.HandoverNotFound):
        await handover.acknowledge(await runtime_for(store), "ho_000000000000", actor=ACTOR)


# --- HTTP -------------------------------------------------------------------------------


class Harness:
    """Builds the stand-in runtime inside the app's lifespan, seeded for the routes."""

    def __init__(self, llm: Any | None = None) -> None:
        self.llm = llm or CountingStub()
        self.runtime: Any = None

    async def factory(self, settings: Settings) -> Runtime:
        from test_api import FakeRuntime as ApiRuntime

        store = open_store(settings)
        await seed_recovery(store)
        await seed_advisory(store, make_advisory())
        await seed_advisory(store, approved_advisory())
        await approvals.approve(
            store, EventBus(), "adv_aaaaaaaaaaaa", expected_version=1, actor="desk:Bo L"
        )

        @dataclass
        class Both(ApiRuntime):
            llm: Any = None
            airports: AirportCatalogue = AIRPORTS
            situations: dict[str, Situation] = field(default_factory=dict)
            traces: list[TraceEvent] = field(default_factory=list)

            def trace(
                self, stage: TraceStage, actor: TraceActor, message: str, **kw: Any
            ) -> TraceEvent:
                event = TraceEvent.new(stage, actor, message, level=kw.get("level", "info"))
                self.traces.append(event)
                return event

        self.runtime = Both(settings=settings, store=store, llm=self.llm)
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
        desk_pin=PIN,
        task_token=TASK_TOKEN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


def make_client(settings: Settings, harness: Harness) -> TestClient:
    app = create_app(settings, runtime_factory=harness.factory)
    app.include_router(router, prefix="/api")
    return TestClient(app)


def signed_in(client: TestClient) -> TestClient:
    response = client.post("/api/desk/login", json={"pin": PIN, "name": DISPATCHER})
    assert response.status_code == 200
    return client


def error_of(response: httpx.Response) -> str:
    return str(response.json()["error"])


def test_the_comms_routes_need_a_desk_session(settings: Settings) -> None:
    with make_client(settings, Harness()) as client:
        assert client.get("/api/desk/messages").status_code == 401
        post = client.post("/api/desk/messages/draft", json={"recovery_id": RECOVERY_ID})
        assert post.status_code == 401
        assert client.get("/api/desk/handover/ho_000000000000").status_code == 401


def test_drafting_listing_and_approving_over_http(settings: Settings) -> None:
    with make_client(settings, Harness()) as client:
        signed_in(client)
        drafted = client.post("/api/desk/messages/draft", json={"recovery_id": RECOVERY_ID})
        assert drafted.status_code == 200
        items = drafted.json()["messages"]
        assert len(items) == 7
        listed = client.get("/api/desk/messages")
        assert {m["id"] for m in listed.json()["messages"]} == {m["id"] for m in items}
        target = next(m for m in items if m["flight_no"] == "RFA101")
        assert target["status"] == "DRAFT"
        assert target["final_bodies"]["en"].startswith("Flight RFA101")

        stale = client.post(f"/api/desk/messages/{target['id']}/approve", json={"version": 9})
        assert stale.status_code == 409
        assert error_of(stale) == "version_conflict"
        assert stale.json()["current"]["id"] == target["id"]

        approved = client.post(f"/api/desk/messages/{target['id']}/approve", json={"version": 1})
        assert approved.status_code == 200
        assert approved.json()["status"] == "APPROVED"
        assert approved.json()["decided_by"] == f"desk:{DISPATCHER}"
        outbound = client.get("/api/outbound").json()["messages"]
        assert target["id"] in [m["advisory_id"] for m in outbound]
        assert {m["destination"] for m in outbound} == {"tephra-outbound"}
        again = client.post(f"/api/desk/messages/{target['id']}/approve", json={"version": 2})
        assert error_of(again) == "invalid_transition"
        assert len(client.get("/api/desk/messages").json()["messages"]) == 6


def test_edit_and_reject_over_http(settings: Settings) -> None:
    with make_client(settings, Harness()) as client:
        signed_in(client)
        items = client.post("/api/desk/messages/draft", json={"recovery_id": RECOVERY_ID}).json()
        first, second = items["messages"][:2]
        edited = client.post(
            f"/api/desk/messages/{first['id']}/edit",
            json={"version": 1, "bodies": {"en": "Edited text."}},
        )
        assert edited.status_code == 200
        assert edited.json()["status"] == "EDITED"
        assert edited.json()["final_bodies"]["en"] == "Edited text."
        bad = client.post(
            f"/api/desk/messages/{second['id']}/edit", json={"version": 1, "bodies": {"en": " "}}
        )
        assert bad.status_code == 422
        assert bad.json()["problems"]
        short = client.post(
            f"/api/desk/messages/{second['id']}/reject", json={"version": 1, "reason": "x"}
        )
        assert short.status_code == 422
        rejected = client.post(
            f"/api/desk/messages/{second['id']}/reject", json={"version": 1, "reason": "wrong"}
        )
        assert rejected.json()["status"] == "REJECTED"
        missing = client.post("/api/desk/messages/msg_000000000000/approve", json={"version": 1})
        assert missing.status_code == 404
        assert (
            client.post("/api/desk/messages/nope/approve", json={"version": 1}).status_code == 404
        )


def test_the_draft_request_needs_exactly_one_source(settings: Settings) -> None:
    with make_client(settings, Harness()) as client:
        signed_in(client)
        both = {"recovery_id": RECOVERY_ID, "advisory_id": "adv_aaaaaaaaaaaa"}
        assert client.post("/api/desk/messages/draft", json=both).status_code == 422
        assert client.post("/api/desk/messages/draft", json={}).status_code == 422
        unknown = client.post("/api/desk/messages/draft", json={"recovery_id": "REC-nope"})
        assert unknown.status_code == 404
        draft_advisory = {"advisory_id": make_advisory().id}
        refused = client.post("/api/desk/messages/draft", json=draft_advisory)
        assert refused.status_code == 409
        assert error_of(refused) == "source_not_approved"
        bad_id = client.post("/api/desk/messages/draft", json={"recovery_id": "../x"})
        assert bad_id.status_code == 404


def test_an_approved_advisory_is_briefed_over_http(settings: Settings) -> None:
    with make_client(settings, Harness()) as client:
        signed_in(client)
        response = client.post("/api/desk/messages/draft", json={"advisory_id": "adv_aaaaaaaaaaaa"})
        (briefing,) = response.json()["messages"]
        assert briefing["kind"] == "CREW_BRIEFING"
        assert list(briefing["final_bodies"]) == ["en"]


def test_a_model_failure_is_a_503_and_stores_nothing(settings: Settings) -> None:
    with make_client(settings, Harness(ScriptedLlm(None))) as client:
        signed_in(client)
        response = client.post("/api/desk/messages/draft", json={"recovery_id": RECOVERY_ID})
        assert response.status_code == 503
        body = response.json()
        assert body["error"] == "ai_unavailable"
        assert body["message"].startswith("AI UNAVAILABLE: ")
        assert client.get("/api/desk/messages").json()["messages"] == []


def test_the_handover_flow_over_http(settings: Settings) -> None:
    since = timeutil.to_iso(AT - timedelta(hours=8))
    with make_client(settings, Harness()) as client:
        signed_in(client)
        made = client.post("/api/desk/handover", json={"since": since, "incoming": "Bo L"})
        assert made.status_code == 200
        brief = made.json()
        assert brief["outgoing"] == DISPATCHER  # defaults to the signed-in name
        assert brief["doc_type"] == "handover"
        assert brief["receiver_ack"] == {"read_back_by": None, "utc": None, "open_drafts": []}
        assert brief["handed_over_open"] == [make_advisory().id]
        fetched = client.get(f"/api/desk/handover/{brief['id']}")
        assert fetched.json() == brief

        acked = client.post(f"/api/desk/handover/{brief['id']}/ack", headers={CSRF_HEADER: "1"})
        assert acked.status_code == 200
        assert acked.json()["receiver_ack"]["read_back_by"] == f"desk:{DISPATCHER}"
        assert acked.json()["receiver_ack"]["open_drafts"] == [make_advisory().id]
        assert (
            client.post(
                "/api/desk/handover/ho_000000000000/ack", headers={CSRF_HEADER: "1"}
            ).status_code
            == 404
        )
        assert client.get("/api/desk/handover/bad").status_code == 404
        forged = client.post(f"/api/desk/handover/{brief['id']}/ack")
        assert forged.status_code == 403


def test_a_handover_the_model_cannot_write_is_a_503(settings: Settings) -> None:
    since = timeutil.to_iso(AT - timedelta(hours=8))
    with make_client(settings, Harness(ScriptedLlm(None))) as client:
        signed_in(client)
        response = client.post("/api/desk/handover", json={"since": since, "incoming": "Bo L"})
        assert response.status_code == 503
        assert response.json()["error"] == "ai_unavailable"
