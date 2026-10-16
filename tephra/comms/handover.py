"""Shift handover brief: WEST (weather, equipment, situation, traffic) plus I-PASS.

Code gathers every fact: the advisories and their states, AI failures, recovery plans,
message drafts, feeds, official areas, discrepancies and the decisions in the audit log since
the shift began. One lite call writes only the two narrative fields (``situation`` and
``contingencies``), each with source ids. Its text passes ``narrative_problems``: every cited
id must be in the evidence the model was given, and every number or time it writes must
appear in that evidence. If the model fails there is no brief and no stand-in
(``AiUnavailable``). The incoming dispatcher taps "Read back" (``acknowledge``); that is
refused while any draft still awaits a decision.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol
from uuid import uuid4

from tephra.agents.answers import Question, Reuse, prompt_version
from tephra.agents.llm import LlmCall, LlmPart
from tephra.agents.validators import first_problems
from tephra.comms.messages import (
    AI_UNAVAILABLE,
    AiUnavailable,
    CommsError,
    CommsRuntime,
    advisory_action,
    decision_lock,
    list_messages,
    text_part,
)
from tephra.comms.models import (
    ContingencyLine,
    CrewPaxMessage,
    DecisionMade,
    EquipmentData,
    HandoverBrief,
    HandoverSeverity,
    MessageStatus,
    OfficialArea,
    OpenAction,
    ReceiverAck,
    SourcedText,
    TrafficRow,
    WeatherAsh,
)
from tephra.config import Airline
from tephra.desk import audit
from tephra.desk.approvals import SYSTEM_ACTOR, list_advisories
from tephra.desk.failures import list_failures
from tephra.models import (
    Advisory,
    AdvisoryStatus,
    AiFailure,
    AuditAction,
    AuditEntry,
    FeedHealth,
    FeedStatus,
    RunMode,
    Situation,
    SseEvent,
    TephraModel,
    TraceStage,
)
from tephra.regdocs.models import DocKind, DocStatus, DocSummary
from tephra.store.base import Collection, Store, Where
from tephra.util import timeutil

__all__ = [
    "HandoverNotFound",
    "HandoverRuntime",
    "acknowledge",
    "draft_handover",
    "get_handover",
    "handover_question",
    "list_handovers",
    "narrative_problems",
    "summary_of",
]

PROMPT_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "agents" / "prompts" / "handover.md"
)
MAX_SITUATION_CHARS: Final = 900
MAX_CONTINGENCIES: Final = 5
MAX_CONTINGENCY_CHARS: Final = 300
FETCH_LIMIT: Final = 200
REPAIR_ECHO_CHARS: Final = 2000
_NUMBER: Final = re.compile(r"\d+(?:[.,:/]\d+)*")
_DECISION_ACTIONS: Final = frozenset(
    {
        AuditAction.APPROVED,
        AuditAction.EDITED,
        AuditAction.REJECTED,
        AuditAction.MESSAGE_DECIDED,
        AuditAction.RECOVERY_DECIDED,
        AuditAction.AI_FAILURE_HANDLED,
    }
)
_OPEN: Final = "DRAFT"
HANDED_OVER_OPEN: Final = "HANDED OVER OPEN: "


class HandoverNotFound(CommsError): ...


class HandoverRuntime(CommsRuntime, Protocol):
    @property
    def situations(self) -> Mapping[str, Situation]: ...


# --- model I/O ---------------------------------------------------------------------------


class NarrativeContingency(TephraModel):
    condition: str
    then: str
    source_ids: list[str]


class Narrative(TephraModel):
    """The only fields the model writes."""

    situation: str
    situation_source_ids: list[str]
    contingencies: list[NarrativeContingency]


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str


# --- gathering (code only) ---------------------------------------------------------------


@dataclass
class Gathered:
    advisories: list[Advisory] = field(default_factory=list)
    failures: list[AiFailure] = field(default_factory=list)  # open ones only
    recovery: list[Mapping[str, Any]] = field(default_factory=list)
    messages: list[CrewPaxMessage] = field(default_factory=list)
    feeds: list[FeedHealth] = field(default_factory=list)
    areas: list[OfficialArea] = field(default_factory=list)
    latest_vaa: datetime | None = None
    disagreements: list[SourcedText] = field(default_factory=list)
    decisions: list[AuditEntry] = field(default_factory=list)

    @property
    def open_advisories(self) -> list[Advisory]:
        return [a for a in self.advisories if a.status is AdvisoryStatus.DRAFT]

    @property
    def open_messages(self) -> list[CrewPaxMessage]:
        return [m for m in self.messages if m.status is MessageStatus.DRAFT]

    @property
    def open_recovery(self) -> list[Mapping[str, Any]]:
        return [doc for doc in self.recovery if doc.get("status") == _OPEN]


async def _gather(runtime: HandoverRuntime, since: datetime) -> Gathered:
    store = runtime.store
    replay = runtime.mode is RunMode.REPLAY
    advisories = [
        advisory
        for advisory in await list_advisories(store, limit=FETCH_LIMIT)
        if advisory.replay == replay
        and advisory.status is not AdvisoryStatus.SUPERSEDED
        and (advisory.status is AdvisoryStatus.DRAFT or advisory.updated_at >= since)
    ]
    messages = [
        message
        for message in await list_messages(store, replay=replay, limit=FETCH_LIMIT)
        if message.status is MessageStatus.DRAFT or message.updated_at >= since
    ]
    recovery = [
        doc
        for doc in await store.list_docs(Collection.RECOVERY, limit=FETCH_LIMIT)
        if doc.get("status") == _OPEN or str(doc.get("created_at", "")) >= timeutil.to_iso(since)
    ]
    entries = await audit.list_entries(store, limit=FETCH_LIMIT)
    gathered = Gathered(
        advisories=advisories,
        failures=await list_failures(store, replay=replay, limit=FETCH_LIMIT),
        recovery=recovery,
        messages=messages,
        feeds=await store.list_feed_states(),
        decisions=sorted(
            (e for e in entries if e.action in _DECISION_ACTIONS and e.at >= since),
            key=lambda entry: entry.at,
        ),
    )
    _add_weather(gathered, runtime.situations)
    return gathered


def _add_weather(gathered: Gathered, situations: Mapping[str, Situation]) -> None:
    areas: dict[tuple[str, str], OfficialArea] = {}
    vaa_times: list[datetime] = []
    for situation in situations.values():
        for layer in situation.official_layers:
            if layer.is_valid(situation.as_of):
                areas[(layer.source_id, layer.layer)] = OfficialArea(
                    source_id=layer.source_id,
                    label=layer.label,
                    base_ft=layer.base_ft,
                    top_ft=layer.top_ft,
                    valid_from=layer.valid_from,
                    valid_to=layer.valid_to,
                )
        vaa_times.extend(vaa.issued_at for vaa in situation.vaas)
        gathered.disagreements.extend(
            SourcedText(text=d.summary, source_ids=[d.id, *d.source_ids])
            for d in situation.discrepancies
        )
    gathered.areas = [areas[key] for key in sorted(areas)]
    gathered.latest_vaa = max(vaa_times, default=None)


def _severity(gathered: Gathered) -> HandoverSeverity:
    """Set by code: an unplanned flight or a draft for a flight already in the hazard is
    critical; any other open draft is active; a live official area, disagreement or stale
    feed is watch."""
    if gathered.failures or any(a.inside_now for a in gathered.open_advisories):
        return "critical"
    if gathered.open_advisories or gathered.open_messages or gathered.open_recovery:
        return "active"
    if gathered.areas or gathered.disagreements or _stale_feeds(gathered.feeds):
        return "watch"
    return "calm"


def _stale_feeds(feeds: Sequence[FeedHealth]) -> list[str]:
    return [
        f"{feed.feed.value} {feed.status.value}"
        + (f" (last good {timeutil.ddhhmmz(feed.last_success_at)})" if feed.last_success_at else "")
        for feed in feeds
        if feed.status in (FeedStatus.STALE, FeedStatus.ERROR)
    ]


def _data_gaps(feeds: Sequence[FeedHealth]) -> list[str]:
    return [
        f"{feed.feed.value} {feed.status.value}"
        for feed in feeds
        if feed.status in (FeedStatus.NEVER, FeedStatus.DISABLED)
    ]


def _entry_text(advisory: Advisory) -> str:
    return "INSIDE NOW" if advisory.inside_now else f"ENTRY IN {advisory.minutes_to_entry} MIN"


def _traffic(gathered: Gathered) -> list[TrafficRow]:
    rows = [
        TrafficRow(
            flight=advisory.proxy_flight,
            plan=advisory_action(advisory),
            status=advisory.status.value.lower(),
            reason=f"{advisory.volcano_name} {advisory.plume_mode.value}, {_entry_text(advisory)}",
            source_ids=[advisory.id],
        )
        for advisory in gathered.advisories
    ]
    rows.extend(
        TrafficRow(
            flight=failure.proxy_flight,
            plan="NO AI PLAN",
            status="ai_failed",
            reason=failure.reason,
            source_ids=[failure.id],
        )
        for failure in gathered.failures
    )
    return rows


def _actions_open(gathered: Gathered, owner: str) -> list[OpenAction]:
    actions = [
        OpenAction(
            owner=owner,
            action=f"{HANDED_OVER_OPEN}decide the advisory for {advisory.proxy_flight}: "
            f"{advisory_action(advisory)}",
            due_utc=None
            if advisory.inside_now
            else advisory.created_at + timedelta(minutes=advisory.minutes_to_entry),
            source_ids=[advisory.id],
        )
        for advisory in gathered.open_advisories
    ]
    actions.extend(
        OpenAction(
            owner=owner,
            action=f"Handle {failure.proxy_flight} by hand: {AI_UNAVAILABLE}, no plan or draft",
            source_ids=[failure.id],
        )
        for failure in gathered.failures
    )
    actions.extend(
        OpenAction(
            owner=owner,
            action=f"{HANDED_OVER_OPEN}decide the {message.kind.value.replace('_', ' ').lower()} "
            f"{message.flight_no or message.tail or ''}".strip(),
            source_ids=[message.id],
        )
        for message in gathered.open_messages
    )
    actions.extend(
        OpenAction(
            owner=owner,
            action=f"{HANDED_OVER_OPEN}decide recovery plan {doc.get('id')}",
            source_ids=[str(doc.get("id"))],
        )
        for doc in gathered.open_recovery
    )
    return actions


def _decisions(gathered: Gathered) -> list[DecisionMade]:
    flights = {advisory.id: advisory.proxy_flight for advisory in gathered.advisories}
    decided: list[DecisionMade] = []
    for entry in gathered.decisions:
        after = entry.after or {}
        subject = (
            flights.get(entry.advisory_id or "")
            or after.get("message_id")
            or after.get("recovery_id")
            or after.get("failure_id")
            or entry.advisory_id
            or ""
        )
        status = after.get("status")
        words = [entry.action.value.replace("_", " ").lower(), str(subject)]
        if status and str(status).lower() not in words[0]:
            words.insert(1, f"({status})")
        ids = [value for value in (entry.advisory_id, after.get("message_id")) if value]
        decided.append(
            DecisionMade(
                by=entry.actor, utc=entry.at, what=" ".join(w for w in words if w), source_ids=ids
            )
        )
    return decided


# --- evidence and narrative --------------------------------------------------------------


def _evidence(gathered: Gathered, brief_parts: Mapping[str, Any]) -> list[Evidence]:
    items: list[Evidence] = []
    for area in gathered.areas:
        items.append(
            Evidence(
                area.source_id,
                f"{area.label}: official ash area from {_fl(area.base_ft)} to {_fl(area.top_ft)},"
                f" valid {timeutil.ddhhmmz(area.valid_from)} to {timeutil.ddhhmmz(area.valid_to)}",
            )
        )
    items.extend(
        Evidence(item.source_ids[0], item.text)
        for item in gathered.disagreements
        if item.source_ids
    )
    items.extend(
        Evidence(
            advisory.id,
            f"advisory for {advisory.proxy_flight} is {advisory.status.value}:"
            f" {advisory_action(advisory)}, {advisory.volcano_name}, {_entry_text(advisory)}",
        )
        for advisory in gathered.advisories
    )
    items.extend(
        Evidence(failure.id, f"{failure.proxy_flight}: {AI_UNAVAILABLE}, {failure.reason}")
        for failure in gathered.failures
    )
    items.extend(
        Evidence(
            message.id,
            f"{message.kind.value.lower()} {message.flight_no or message.tail or ''}"
            f" is {message.status.value}",
        )
        for message in gathered.messages
    )
    items.extend(
        Evidence(str(doc.get("id")), f"recovery plan is {doc.get('status')}")
        for doc in gathered.recovery
    )
    items.extend(
        Evidence(f"feed:{text.split()[0]}", f"feed {text}") for text in brief_parts["feeds_stale"]
    )
    return items


def _fl(feet: int) -> str:
    return f"FL{feet // 100:03d}"


def _facts_json(
    evidence: Sequence[Evidence],
    *,
    now: datetime,
    since: datetime,
    decisions: Sequence[DecisionMade],
    airline: Airline,
) -> str:
    facts = {
        "airline": airline.label,
        "as_of": timeutil.ddhhmmz(now),
        "shift_from": timeutil.ddhhmmz(since),
        "evidence": [{"id": item.id, "text": item.text} for item in evidence],
        # No dispatcher names: Gemini sees public feed content and code-written facts only.
        "decisions_in_shift": [f"{timeutil.ddhhmmz(d.utc)} {d.what}" for d in decisions],
    }
    return json.dumps(facts, ensure_ascii=False, indent=1)


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def narrative_problems(
    narrative: Narrative, *, facts_text: str, evidence_ids: set[str]
) -> list[str]:
    """Upper-case, code-written problems; empty means the narrative is accepted."""
    problems: list[str] = []
    situation = narrative.situation.strip()
    if not situation:
        problems.append("SITUATION IS EMPTY")
    if len(situation) > MAX_SITUATION_CHARS:
        problems.append(f"SITUATION LONGER THAN {MAX_SITUATION_CHARS} CHARACTERS")
    if len(narrative.contingencies) > MAX_CONTINGENCIES:
        problems.append(f"MORE THAN {MAX_CONTINGENCIES} CONTINGENCIES")
    cited = [("SITUATION", situation, narrative.situation_source_ids)]
    for position, line in enumerate(narrative.contingencies, start=1):
        text = f"{line.condition} {line.then}".strip()
        if not line.condition.strip() or not line.then.strip():
            problems.append(f"CONTINGENCY {position} NEEDS BOTH A CONDITION AND AN ACTION")
        if len(text) > MAX_CONTINGENCY_CHARS:
            problems.append(
                f"CONTINGENCY {position} LONGER THAN {MAX_CONTINGENCY_CHARS} CHARACTERS"
            )
        cited.append((f"CONTINGENCY {position}", text, line.source_ids))
    known = _numbers(facts_text)
    for name, text, ids in cited:
        if evidence_ids and not ids:
            problems.append(f"{name} CITES NO SOURCE ID")
        unknown = sorted(set(ids) - evidence_ids)
        if unknown:
            problems.append(f"{name} CITES IDS NOT IN THE EVIDENCE: {', '.join(unknown)}")
        invented = sorted(_numbers(text) - known)
        if invented:
            problems.append(
                f"{name} HAS NUMBERS OR TIMES NOT IN THE EVIDENCE: {', '.join(invented)}"
            )
    return problems


def _stub_narrative(evidence: Sequence[Evidence]) -> Narrative:
    ids = [evidence[0].id] if evidence else []
    return Narrative(
        situation="The sections of this brief list the situation as code gathered it.",
        situation_source_ids=ids,
        contingencies=[],
    )


def handover_question(facts_text: str) -> Question:
    """A handover narrative is reused only for identical inputs: every fact the model is given
    but the clock line (``as_of``), whose figures the checks then hold the narrative to."""
    facts = {key: value for key, value in json.loads(facts_text).items() if key != "as_of"}
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return Question("handover", {"prompt": prompt_version(system), "facts": facts})


async def _narrate(
    runtime: HandoverRuntime, evidence: Sequence[Evidence], facts_text: str
) -> tuple[Narrative, LlmCall, datetime]:
    """One lite call and at most one repair; ``AiUnavailable`` when it cannot be checked.
    The same model's narrative for identical inputs is used when it passes the checks now;
    with the narrative comes the time the model wrote it."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    parts = [text_part(facts_text, "facts")]
    ids = {item.id for item in evidence}
    answers = runtime.answers
    reuse = None if answers is None else answers.reuse(handover_question(facts_text))
    if reuse is not None and (held := await _known_narrative(reuse, runtime, facts_text, ids)):
        return held

    async def ask(extra: Sequence[LlmPart]) -> tuple[Narrative | None, LlmCall]:
        return await runtime.llm.structured(
            tier="lite",
            system=system,
            parts=[*parts, *extra],
            schema=Narrative,
            stub=lambda: _stub_narrative(evidence),
        )

    def check(answer: Narrative | None, call: LlmCall) -> list[str]:
        if answer is None:
            return [f"NO ANSWER RETURNED ({call.error or 'unknown error'})"]
        return narrative_problems(answer, facts_text=facts_text, evidence_ids=ids)

    answer, call = await ask([])
    first = call
    problems = check(answer, call)
    if problems and (answer is not None or call.raw_text) and runtime.llm.name != "stub":
        listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
        previous = (
            json.dumps(answer.model_dump(mode="json"), ensure_ascii=False, indent=1)
            if answer is not None
            else (call.raw_text or "")[:REPAIR_ECHO_CHARS]
        )
        repair = text_part(
            f"Code checks rejected your answer:\n{listed}\nYour answer was:\n{previous}\n"
            "Write situation and contingencies again, fixing every problem.",
            "repair",
        )
        answer, call = await ask([repair])
        problems = check(answer, call)
    if answer is None or problems:
        reason = (
            f"NO ANSWER RETURNED ({call.error or 'unknown error'})"
            if answer is None
            else f"NARRATIVE FAILED CHECKS AFTER REPAIR: {'; '.join(first_problems(problems, 3))}"
        )
        raise AiUnavailable(reason)
    written_at = timeutil.now()
    if reuse is not None:
        await reuse.keep(
            call.model_id,
            answer.model_dump(mode="json"),
            prompt_hash=first.prompt_hash,
            answered_at=written_at,
        )
    return answer, first, written_at


async def _known_narrative(
    reuse: Reuse, runtime: HandoverRuntime, facts_text: str, ids: set[str]
) -> tuple[Narrative, LlmCall, datetime] | None:
    found = await reuse.recall_as(runtime.llm.model_id("lite"), Narrative)
    if found is None:
        return None
    answer, narrative = found
    problems = narrative_problems(narrative, facts_text=facts_text, evidence_ids=ids)
    if problems:
        reuse.rejected(problems)
        return None
    call = LlmCall(
        backend=runtime.llm.name, model_id=answer.model_id, prompt_hash=answer.prompt_hash
    )
    return narrative, call, answer.shown_at(timeutil.now())


# --- drafting ----------------------------------------------------------------------------


async def draft_handover(
    runtime: HandoverRuntime, since: datetime, outgoing: str, incoming: str
) -> HandoverBrief:
    now = timeutil.now()
    gathered = await _gather(runtime, since)
    feeds_stale = _stale_feeds(gathered.feeds)
    decisions = _decisions(gathered)
    evidence = _evidence(gathered, {"feeds_stale": feeds_stale})
    facts_text = _facts_json(
        evidence, now=now, since=since, decisions=decisions, airline=runtime.airline
    )
    try:
        narrative, call, written_at = await _narrate(runtime, evidence, facts_text)
    except AiUnavailable as exc:
        await _record_failure(runtime, exc.reason, actor=outgoing)
        raise
    backend = runtime.llm.name
    runtime.trace(
        TraceStage.MESSAGES,
        "stub" if backend == "stub" else "gemini",
        f"HANDOVER BRIEF ({'NO MODEL' if backend == 'stub' else 'AI-WRITTEN'})",
    )
    brief = HandoverBrief(
        id="ho_" + uuid4().hex[:12],
        created_at=now,
        replay=runtime.mode is RunMode.REPLAY,
        fictional_airline=runtime.airline.fictional,
        shift_from=since,
        shift_to=now,
        outgoing=outgoing,
        incoming=incoming,
        severity=_severity(gathered),
        weather_ash=WeatherAsh(
            official_areas=gathered.areas,
            latest_vaa_utc=gathered.latest_vaa,
            disagreements=gathered.disagreements,
            source_ids=[area.source_id for area in gathered.areas],
        ),
        equipment_data=EquipmentData(feeds_stale=feeds_stale, data_gaps=_data_gaps(gathered.feeds)),
        situation=SourcedText(
            text=narrative.situation.strip(), source_ids=narrative.situation_source_ids
        ),
        traffic=_traffic(gathered),
        actions_open=_actions_open(gathered, incoming),
        handed_over_open=[
            *(a.id for a in gathered.open_advisories),
            *(m.id for m in gathered.open_messages),
            *(str(doc.get("id")) for doc in gathered.open_recovery),
        ],
        contingencies=[
            ContingencyLine(
                condition=line.condition.strip(),
                then=line.then.strip(),
                source_ids=line.source_ids,
            )
            for line in narrative.contingencies
        ],
        decisions_made=decisions,
        evidence_ids=[item.id for item in evidence],
        narrative_at=written_at,
        llm_backend=backend,
        model_id=call.model_id,
        prompt_hash=call.prompt_hash,
    )
    await runtime.store.put(Collection.DOCS, brief.id, brief.model_dump(mode="json"))
    await audit.record(
        runtime.store,
        actor=f"desk:{outgoing}",
        action=AuditAction.DOC_DRAFTED,
        after={"doc_type": brief.doc_type, "handover_id": brief.id, "incoming": incoming},
        model_id=brief.model_id,
        prompt_hash=brief.prompt_hash,
    )
    runtime.bus.publish(SseEvent.DOC, summary_of(brief))
    return brief


async def _record_failure(runtime: HandoverRuntime, reason: str, *, actor: str) -> None:
    runtime.trace(
        TraceStage.MESSAGES,
        "code",
        f"HANDOVER {AI_UNAVAILABLE} ({reason}): NO BRIEF WRITTEN",
        level="error",
    )
    await audit.record(
        runtime.store,
        actor=SYSTEM_ACTOR,
        action=AuditAction.AI_FAILED,
        after={"stage": "handover", "requested_by": actor},
        model_id=runtime.llm.model_id("lite"),
        note=f"{AI_UNAVAILABLE}: {reason}",
    )


# --- read-back ---------------------------------------------------------------------------


async def get_handover(store: Store, handover_id: str) -> HandoverBrief | None:
    doc = await store.get(Collection.DOCS, handover_id)
    if doc is None or doc.get("doc_type") != "handover":
        return None
    return HandoverBrief.model_validate(doc)


async def list_handovers(
    store: Store, *, replay: bool | None = None, limit: int = 20
) -> list[HandoverBrief]:
    """Newest first; ``replay`` keeps only the briefs made in that mode."""
    docs = await store.query(
        Collection.DOCS,
        [Where("doc_type", "==", "handover")],
        order_by="created_at",
        descending=True,
        limit=FETCH_LIMIT,
    )
    briefs = [HandoverBrief.model_validate(doc) for doc in docs]
    return [b for b in briefs if replay is None or b.replay == replay][:limit]


def summary_of(brief: HandoverBrief) -> DocSummary:
    """The ``doc`` SSE payload of a brief: the same shape as for SRA and VAR drafts."""
    read_back = brief.receiver_ack.read_back_by is not None
    return DocSummary(
        id=brief.id,
        kind=DocKind.HANDOVER,
        status=DocStatus.ACKNOWLEDGED if read_back else DocStatus.DRAFT,
        title=f"Handover brief: {brief.outgoing} to {brief.incoming}",
        created_at=brief.created_at,
        updated_at=brief.receiver_ack.utc or brief.created_at,
        replay=brief.replay,
        signed_roles=[],
        missing_roles=[],
        llm_backend=brief.llm_backend,
    )


async def acknowledge(runtime: HandoverRuntime, handover_id: str, *, actor: str) -> HandoverBrief:
    """The receiver's read-back (I-PASS synthesis). Drafts still open are not a reason to
    refuse it: the brief lists them as handed over open and the read-back records which were
    still open. A second read-back keeps the first."""
    store = runtime.store
    async with decision_lock(store):
        brief = await get_handover(store, handover_id)
        if brief is None:
            raise HandoverNotFound(handover_id)
        if brief.receiver_ack.read_back_by is not None:
            return brief
        still_open = await _open_drafts(runtime)
        acked = brief.model_copy(
            update={
                "receiver_ack": ReceiverAck(
                    read_back_by=actor, utc=timeutil.now(), open_drafts=still_open
                )
            }
        )
        await store.put(Collection.DOCS, handover_id, acked.model_dump(mode="json"))
    await audit.record(
        store,
        actor=actor,
        action=AuditAction.HANDOVER_ACKED,
        after={
            "doc_type": "handover",
            "handover_id": handover_id,
            "read_back_by": actor,
            "handed_over_open": acked.receiver_ack.open_drafts,
        },
    )
    runtime.bus.publish(SseEvent.DOC, summary_of(acked))
    return acked


async def _open_drafts(runtime: HandoverRuntime) -> list[str]:
    """Ids of advisories, messages and recovery plans still in DRAFT in the current mode."""
    store = runtime.store
    replay = runtime.mode is RunMode.REPLAY
    advisories = await list_advisories(store, status=AdvisoryStatus.DRAFT, limit=FETCH_LIMIT)
    messages = await list_messages(
        store, status=MessageStatus.DRAFT, replay=replay, limit=FETCH_LIMIT
    )
    recovery = await store.list_docs(Collection.RECOVERY, limit=FETCH_LIMIT)
    return [
        *(a.id for a in advisories if a.replay == replay),
        *(m.id for m in messages),
        *(str(doc.get("id")) for doc in recovery if doc.get("status") == _OPEN),
    ]
