"""Duty Officer: the coordinator that hands each tick's AI work to the specialist agents.

Code decides what work is due, with the same gates as before: a volcano whose plume needs
reading, an exposed flight to plan in a new cone or a more urgent bucket, a changed set of
closed airports, a region newly carrying exposed flights. The Duty Officer (a Google ADK
``LlmAgent`` on the lite tier) gets that work list with a code-written digest of the picture
and decides the order and what can wait. It delegates through tools, one per specialist:

    assess_volcanoes -> Satellite Reader + Plume Reader, then cone and exposure (code)
    plan_flights     -> Exposure Planner (ADK) + Dispatch Drafter
    run_recovery     -> recovery agent (ADK) over the CP-SAT solver
    draft_sra        -> SRA drafter
    defer            -> leave optional work for the next run, with a reason
    submit_brief     -> the operational brief for the dispatchers (validated)

Every specialist keeps its own validators, so the Duty Officer never writes advice itself.
Code holds the safety line: a plume read is done before that volcano's flights are planned,
mandatory items (a flight inside or about to enter the area, a volcano with no official area
but reported ash) cannot be deferred, and a mandatory item left undone when the run ends goes
to the Desk as AI UNAVAILABLE. There is no substitute dispatcher. ``TEPHRA_LLM=stub`` runs the
offline stand-in (everything, most urgent first) labelled NO MODEL.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, Protocol
from uuid import uuid4

from tephra.agents.adk_runtime import ModelGuard, summarise
from tephra.agents.llm import LlmBackend, LlmPart, prompt_hash, temperature_for
from tephra.agents.validators import clock_problems, first_problems
from tephra.config import Settings
from tephra.models import (
    DutyBrief,
    DutyDeferral,
    DutyDispatch,
    DutyItem,
    DutyItemKind,
    DutyPriority,
    DutyRun,
    TraceActor,
    TraceEvent,
    TraceSink,
    TraceStage,
)
from tephra.util import timeutil

if TYPE_CHECKING:
    from google.adk.agents import LlmAgent
    from google.adk.runners import InMemoryRunner

__all__ = [
    "PROMPT_PATH",
    "DutyExecutor",
    "DutyToolkit",
    "RecordedDuty",
    "build_duty_agent",
    "run_duty_officer",
    "validate_brief",
]

logger = logging.getLogger(__name__)

PROMPT_PATH: Final[Path] = Path(__file__).resolve().parent / "prompts" / "duty_officer.md"
ADK_APP_NAME: Final = "tephra_duty_officer"
ADK_USER_ID: Final = "tephra"
AGENT_NAME: Final = "tephra_duty_officer"
MAX_MODEL_TURNS: Final = 12
"""Model turns per run: one per delegation round, the brief, and one repair."""
SUMMARY_MAX_CHARS: Final = 500
WHY_MAX_CHARS: Final = 160
WATCH_MAX_ITEMS: Final = 4
WATCH_MAX_CHARS: Final = 160
_NUMBER: Final = re.compile(r"\d+(?:\.\d+)?")
_PROXY_FLIGHT: Final = re.compile(r"\bRFA\d{3,4}\b")
_ID_TOKEN: Final = re.compile(
    r"\b[A-Za-z]{2,5}[-_][0-9a-f]{8,}\b"  # DI-, DOC-, AIF-, CONE-, adv_ ... ids
    r"|\b[0-9a-f]{6}:\d+\b"  # flight ids: ICAO hex and volcano number
    r"|\b[0-9a-f]{32,}\b"  # hashes
)

Outcome = Literal["ACCEPTED", "REPAIRED", "MODEL_FAILED", "STUB"]


class DutyExecutor(Protocol):
    """What the Duty Officer's tools act on; the runtime implements it with the specialists.

    Each call returns a code-written result for the model and the trace. ``assess`` also
    returns the PLAN items the new cone made due (new or more urgent entries)."""

    async def assess(self, volcano_id: str) -> tuple[dict[str, Any], list[DutyItem]]: ...

    async def plan(self, flight_id: str) -> dict[str, Any]: ...

    async def recover(self) -> dict[str, Any]: ...

    async def draft_sra(self, region: str) -> dict[str, Any]: ...


# --- the toolkit: work list bookkeeping behind every tool ------------------------------------


@dataclass
class DutyToolkit:
    """The work list as the run goes: what is pending, dispatched, deferred or replaced.

    ``evidence`` collects every code-written text the model saw (the digest, each tool result),
    so the brief's numbers and flights can be checked against it."""

    executor: DutyExecutor
    trace: TraceSink | None
    items: dict[str, DutyItem] = field(default_factory=dict)
    done: set[str] = field(default_factory=set)
    replaced: set[str] = field(default_factory=set)
    deferred: dict[str, str] = field(default_factory=dict)
    dispatches: list[DutyDispatch] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    brief: DutyBrief | None = None
    brief_problems: list[str] = field(default_factory=list)

    @classmethod
    def of(
        cls, worklist: Iterable[DutyItem], executor: DutyExecutor, trace: TraceSink | None
    ) -> "DutyToolkit":
        toolkit = cls(executor=executor, trace=trace)
        for item in worklist:
            toolkit.items[item.id] = item
        return toolkit

    def pending(self, kind: DutyItemKind | None = None) -> list[DutyItem]:
        """Open items, most urgent first."""
        open_items = [
            item
            for item_id, item in self.items.items()
            if item_id not in self.done
            and item_id not in self.replaced
            and (kind is None or item.kind is kind)
        ]
        return sorted(open_items, key=lambda item: (item.urgency, item.label))

    def undispatched_mandatory(self) -> list[DutyItem]:
        return [item for item in self.pending() if item.mandatory]

    def worklist(self) -> list[DutyItem]:
        return [item for item_id, item in self.items.items() if item_id not in self.replaced]

    def add(self, new_items: Iterable[DutyItem]) -> list[DutyItem]:
        """New work from a delegation; an older item for the same flight or volcano and kind
        is replaced (a new cone or bucket supersedes it). Returns the items really added."""
        added: list[DutyItem] = []
        for item in new_items:
            if item.id in self.items:
                continue
            for old in self.pending(item.kind):
                if old.subject == item.subject:
                    self.replaced.add(old.id)
            self.items[item.id] = item
            added.append(item)
        return added

    # --- delegations (each one a tool) ------------------------------------------------------

    async def assess_volcanoes(self, volcano_ids: Sequence[str]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for volcano_id in _unique(volcano_ids):
            item = self._pending_for(DutyItemKind.ASSESS, volcano_id)
            if item is None:
                results.append({"volcano_id": volcano_id, "error": "NO PLUME READ IS DUE"})
                continue
            started = time.perf_counter()
            result, new_items = await self.executor.assess(volcano_id)
            added = self.add(new_items)
            result = {**result, "new_plan_items": [_item_view(new) for new in added]}
            self._dispatched("assess_volcanoes", [item.id], result, started)
            results.append(result)
        return self._seen({"results": results, "pending": self._pending_view()})

    async def plan_flights(self, flight_ids: Sequence[str]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for flight_id in _unique(flight_ids):
            item = self._pending_for(DutyItemKind.PLAN, flight_id)
            if item is None:
                results.append({"flight_id": flight_id, "error": "NO PLAN IS DUE FOR THIS FLIGHT"})
                continue
            if item.volcano_id and self._pending_for(DutyItemKind.ASSESS, item.volcano_id):
                results.append(
                    {
                        "flight_id": flight_id,
                        "error": f"ASSESS VOLCANO {item.volcano_id} FIRST: ITS PLUME READ IS DUE",
                    }
                )
                continue
            started = time.perf_counter()
            result = await self.executor.plan(flight_id)
            self._dispatched("plan_flights", [item.id], result, started)
            results.append(result)
        return self._seen({"results": results, "pending": self._pending_view()})

    async def run_recovery(self) -> dict[str, Any]:
        item = self._pending_for(DutyItemKind.RECOVER, "network")
        if item is None:
            return self._seen({"error": "NO NETWORK RECOVERY IS DUE"})
        started = time.perf_counter()
        result = await self.executor.recover()
        self._dispatched("run_recovery", [item.id], result, started)
        return self._seen({**result, "pending": self._pending_view()})

    async def draft_sra(self, region: str) -> dict[str, Any]:
        item = self._pending_for(DutyItemKind.SRA, region)
        if item is None:
            return self._seen({"error": f"NO SRA IS DUE FOR REGION {region}"})
        started = time.perf_counter()
        result = await self.executor.draft_sra(region)
        self._dispatched("draft_sra", [item.id], result, started)
        return self._seen({**result, "pending": self._pending_view()})

    def defer(self, item_ids: Sequence[str], reason: str) -> dict[str, Any]:
        reason = " ".join(reason.split())[:WHY_MAX_CHARS]
        refused: list[dict[str, str]] = []
        accepted: list[str] = []
        for item_id in _unique(item_ids):
            item = self.items.get(item_id)
            if item is None or item_id in self.done or item_id in self.replaced:
                refused.append({"item_id": item_id, "error": "NOT AN OPEN ITEM"})
            elif item.mandatory:
                refused.append({"item_id": item_id, "error": "MANDATORY: DISPATCH IT THIS RUN"})
            elif not reason:
                refused.append({"item_id": item_id, "error": "GIVE A REASON"})
            else:
                self.deferred[item_id] = reason
                accepted.append(item_id)
        if accepted:
            _emit(self.trace, "adk", f"Duty Officer deferred {len(accepted)} item(s): {reason}")
        return self._seen({"deferred": accepted, "refused": refused})

    def submit_brief(
        self,
        summary: str,
        priority_item_ids: Sequence[str],
        priority_reasons: Sequence[str],
        watch: Sequence[str],
    ) -> dict[str, Any]:
        brief = DutyBrief(
            summary=" ".join(summary.split()),
            priorities=[
                DutyPriority(item_id=item_id, why=" ".join(why.split()))
                for item_id, why in zip(priority_item_ids, priority_reasons, strict=False)
            ],
            watch=[" ".join(line.split()) for line in watch if line.strip()],
        )
        problems = validate_brief(brief, self)
        if len(priority_item_ids) != len(priority_reasons):
            problems.insert(0, "GIVE ONE REASON PER PRIORITY ITEM")
        self.brief, self.brief_problems = (None, problems) if problems else (brief, [])
        return {"status": "rejected", "problems": problems} if problems else {"status": "ok"}

    # --- helpers --------------------------------------------------------------------------

    def _pending_for(self, kind: DutyItemKind, subject: str) -> DutyItem | None:
        return next((item for item in self.pending(kind) if item.subject == subject), None)

    def _dispatched(
        self, tool: str, item_ids: list[str], result: dict[str, Any], started: float
    ) -> None:
        self.done.update(item_ids)
        for item_id in item_ids:
            self.deferred.pop(item_id, None)
        ok = "error" not in result and result.get("status") != "ai_unavailable"
        summary = str(result.get("summary") or summarise(result))
        ms = round((time.perf_counter() - started) * 1000)
        self.dispatches.append(
            DutyDispatch(tool=tool, item_ids=item_ids, ok=ok, result=summary, ms=ms)
        )
        _emit(
            self.trace, "adk", f"Duty Officer -> {tool}: {summary}", level="info" if ok else "warn"
        )

    def _pending_view(self) -> list[dict[str, Any]]:
        return [_item_view(item) for item in self.pending()]

    def _seen(self, result: dict[str, Any]) -> dict[str, Any]:
        self.evidence.append(json.dumps(result, default=str, ensure_ascii=False))
        return result


def validate_brief(brief: DutyBrief, toolkit: DutyToolkit) -> list[str]:
    """Upper-case, code-written problems; empty means the brief is accepted."""
    problems: list[str] = []
    if not brief.summary:
        problems.append("SUMMARY IS EMPTY")
    if len(brief.summary) > SUMMARY_MAX_CHARS:
        problems.append(f"SUMMARY LONGER THAN {SUMMARY_MAX_CHARS} CHARACTERS")
    if len(brief.watch) > WATCH_MAX_ITEMS:
        problems.append(f"MORE THAN {WATCH_MAX_ITEMS} WATCH ITEMS")
    known = set(toolkit.items)
    seen: set[str] = set()
    for priority in brief.priorities:
        if priority.item_id not in known:
            problems.append(f"UNKNOWN ITEM {priority.item_id} IN PRIORITIES")
        if priority.item_id in seen:
            problems.append(f"ITEM {priority.item_id} LISTED TWICE")
        seen.add(priority.item_id)
        if not priority.why or len(priority.why) > WHY_MAX_CHARS:
            problems.append(f"REASON FOR {priority.item_id} EMPTY OR LONGER THAN {WHY_MAX_CHARS}")
    texts = [
        ("summary", brief.summary),
        *((f"priority {p.item_id}", p.why) for p in brief.priorities),
        *((f"watch {index + 1}", line) for index, line in enumerate(brief.watch)),
    ]
    problems.extend(
        f"WATCH ITEM {index + 1} LONGER THAN {WATCH_MAX_CHARS} CHARACTERS"
        for index, line in enumerate(brief.watch)
        if len(line) > WATCH_MAX_CHARS
    )
    for name, text in texts:
        problems.extend(clock_problems(text, name))
    problems.extend(_invented(texts, toolkit))
    return problems


def _invented(texts: Sequence[tuple[str, str]], toolkit: DutyToolkit) -> list[str]:
    """Numbers and RFA flight numbers in the brief must appear in what the model was shown.

    Ids and hashes are taken out of that text first: their digits are not facts, and a number
    the model made up must not pass because it happens to sit inside a hash."""
    labels = "\n".join(item.label for item in toolkit.items.values())
    evidence = _ID_TOKEN.sub(" ", "\n".join([*toolkit.evidence, labels]))
    numbers = {_normal_number(token) for token in _NUMBER.findall(evidence)}
    flights = set(_PROXY_FLIGHT.findall(evidence))
    problems: list[str] = []
    for name, text in texts:
        for token in _NUMBER.findall(_ID_TOKEN.sub(" ", text)):
            if _normal_number(token) not in numbers:
                problems.append(f"NUMBER {token} IN {name.upper()} IS NOT IN THE INPUT")
        for flight in _PROXY_FLIGHT.findall(text):
            if flight not in flights:
                problems.append(f"FLIGHT {flight} IN {name.upper()} IS NOT IN THE INPUT")
    return problems


def _normal_number(token: str) -> str:
    value = float(token)
    return str(int(value)) if value.is_integer() else str(value)


# --- the run --------------------------------------------------------------------------------


@dataclass
class _Run:
    outcome: Outcome = "ACCEPTED"
    problems: list[str] = field(default_factory=list)
    turns: int = 0
    recorded_answer: str | None = None


class RecordedDuty(NamedTuple):
    """A REPLAY loop's first-pass run given the same question (the same instructions, picture
    digest and work list, so the same prompt hash): its delegations, deferrals and brief, made
    again in the same order (each specialist checks its own work again)."""

    run: DutyRun
    label: str


async def run_duty_officer(
    worklist: Sequence[DutyItem],
    executor: DutyExecutor,
    llm: LlmBackend,
    *,
    digest: str,
    settings: Settings,
    trigger: Literal["tick", "adsb"],
    replay: bool,
    trace: TraceSink | None = None,
    recall: Callable[[str], Awaitable[RecordedDuty | None]] | None = None,
) -> DutyRun:
    """One Duty Officer run over ``worklist``. It never raises for model trouble: a run with no
    valid brief is ``MODEL_FAILED``, and the caller sends undone mandatory items to the Desk.
    ``recall`` (REPLAY only) finds the first pass's run for this run's prompt hash; that run is
    made again, and when its brief no longer passes the checks the model finishes the run."""
    started_at = timeutil.now()
    toolkit = DutyToolkit.of(worklist, executor, trace)
    toolkit.evidence.append(digest)
    system = PROMPT_PATH.read_text(encoding="utf-8")
    task = _task_text(digest, toolkit)
    p_hash = prompt_hash(system, [LlmPart.of_text(task)])
    run = _Run()
    model_id = llm.model_id("lite")
    if llm.name == "stub":
        await _stub_dispatch(toolkit)
        run.outcome = "STUB"
    else:
        recorded = await recall(p_hash) if recall is not None else None
        if recorded is not None and await _replay_recorded(toolkit, recorded, trace):
            run.outcome = recorded.run.outcome
            run.recorded_answer = recorded.label
            model_id, p_hash = recorded.run.model_id, recorded.run.prompt_hash
        else:
            _emit(trace, "adk", f"Duty Officer: {len(worklist)} item(s) to dispatch ({trigger})")
            task = _task_text(digest, toolkit)
            try:
                await _run_agent(toolkit, llm, run, task, settings)
            except Exception as exc:  # ADK or API failure: no substitute dispatcher
                logger.warning("duty officer run failed: %s", type(exc).__name__)
                run.problems = [*run.problems, f"DUTY OFFICER ERROR: {type(exc).__name__}"]
        if toolkit.brief is None:
            run.outcome = "MODEL_FAILED"
    undone = toolkit.undispatched_mandatory()
    duty = DutyRun(
        id=f"DUTY-{uuid4().hex[:12]}",
        started_at=started_at,
        finished_at=timeutil.now(),
        replay=replay,
        trigger=trigger,
        worklist=toolkit.worklist(),
        dispatches=toolkit.dispatches,
        deferred=[DutyDeferral(item_id=k, reason=v) for k, v in toolkit.deferred.items()],
        brief=toolkit.brief,
        outcome=run.outcome,
        llm_backend=llm.name,
        model_id=model_id,
        prompt_hash=p_hash,
        turns=run.turns,
        validation_errors=[*run.problems, *toolkit.brief_problems],
        undispatched=[item.id for item in undone],
        recorded_answer=run.recorded_answer,
    )
    _emit_result(trace, duty)
    return duty


async def _replay_recorded(
    toolkit: DutyToolkit, recorded: RecordedDuty, trace: TraceSink | None
) -> bool:
    """Make the recorded run's delegations and deferrals again, in its order, and submit its
    brief. True when the brief passed the checks and no mandatory item is left."""
    first = recorded.run
    _emit(trace, "adk", f"Duty Officer: the same work as on the first pass ({recorded.label})")
    for dispatch in first.dispatches:
        subjects = [toolkit.items[i].subject for i in dispatch.item_ids if i in toolkit.items]
        if dispatch.tool == "assess_volcanoes":
            await toolkit.assess_volcanoes(subjects)
        elif dispatch.tool == "plan_flights":
            await toolkit.plan_flights(subjects)
        elif dispatch.tool == "run_recovery":
            await toolkit.run_recovery()
        elif dispatch.tool == "draft_sra":
            for region in subjects:
                await toolkit.draft_sra(region)
    for deferral in first.deferred:
        toolkit.defer([deferral.item_id], deferral.reason)
    brief = first.brief
    if brief is not None:
        toolkit.submit_brief(
            brief.summary,
            [priority.item_id for priority in brief.priorities],
            [priority.why for priority in brief.priorities],
            brief.watch,
        )
    if toolkit.brief is not None and not toolkit.undispatched_mandatory():
        return True
    _emit(
        trace,
        "code",
        "The first pass's brief no longer fits this work; the Duty Officer model finishes the run",
        level="warn",
    )
    return False


async def _stub_dispatch(toolkit: DutyToolkit) -> None:
    """``TEPHRA_LLM=stub`` only (labelled NO MODEL): every item, most urgent first, plume
    reads before plans."""
    await toolkit.assess_volcanoes([item.subject for item in toolkit.pending(DutyItemKind.ASSESS)])
    await toolkit.plan_flights([item.subject for item in toolkit.pending(DutyItemKind.PLAN)])
    if toolkit.pending(DutyItemKind.RECOVER):
        await toolkit.run_recovery()
    for item in toolkit.pending(DutyItemKind.SRA):
        await toolkit.draft_sra(item.subject)
    order = [item.id for item in sorted(toolkit.worklist(), key=lambda item: item.urgency)]
    dispatched = len(toolkit.dispatches)
    toolkit.brief = DutyBrief(
        summary=f"NO MODEL: {dispatched} delegation(s) made in urgency order.",
        priorities=[
            DutyPriority(item_id=item_id, why="NO MODEL: urgency order") for item_id in order
        ],
    )


async def _run_agent(
    toolkit: DutyToolkit, llm: LlmBackend, run: _Run, task: str, settings: Settings
) -> None:
    from google.adk.runners import InMemoryRunner

    guard = ModelGuard(llm, max_turns=MAX_MODEL_TURNS)
    agent = build_duty_agent(
        settings.model_lite,
        toolkit,
        before_model_callback=guard,
        on_model_error_callback=guard.on_model_error,
    )
    runner = InMemoryRunner(agent=agent, app_name=ADK_APP_NAME)
    try:
        session = await runner.session_service.create_session(
            app_name=ADK_APP_NAME, user_id=ADK_USER_ID
        )
        await _turn(runner, session.id, task, settings)
        unfinished = toolkit.brief is None or toolkit.undispatched_mandatory()
        if unfinished and guard.stop_reason is None:
            run.outcome = "REPAIRED"
            await _turn(runner, session.id, _repair_text(toolkit), settings)
        if guard.stop_reason is not None:
            run.problems.append(guard.stop_reason)
    finally:
        run.turns = guard.turns
        await runner.close()


async def _turn(
    runner: "InMemoryRunner", session_id: str, message: str, settings: Settings
) -> None:
    from google.genai import types

    content = types.Content(role="user", parts=[types.Part(text=message)])
    async with asyncio.timeout(settings.duty_run_timeout_s):
        async for _ in runner.run_async(
            user_id=ADK_USER_ID, session_id=session_id, new_message=content
        ):
            pass


def build_duty_agent(
    model: str,
    toolkit: DutyToolkit,
    *,
    before_model_callback: Callable[..., Any] | None = None,
    on_model_error_callback: Callable[..., Any] | None = None,
) -> "LlmAgent":
    """The Duty Officer as an ADK ``LlmAgent`` whose tools delegate to the specialists."""
    from google.adk.agents import LlmAgent
    from google.genai import types

    async def assess_volcanoes(volcano_ids: list[str]) -> dict[str, Any]:
        """Hand the plume read of these volcanoes (volcano ids from ASSESS items) to the
        Satellite Reader and the Plume Reader; code then rebuilds each hazard cone and the
        exposure. Returns each volcano's new cone and the PLAN items the new cone made due."""
        return await toolkit.assess_volcanoes(volcano_ids)

    async def plan_flights(flight_ids: list[str]) -> dict[str, Any]:
        """Hand these exposed flights (flight ids from PLAN items), in the order given, to the
        Exposure Planner and the Dispatch Drafter. A flight whose volcano still has a plume
        read due is refused: assess that volcano first. Returns each flight's draft advice or
        why there is none."""
        return await toolkit.plan_flights(flight_ids)

    async def run_recovery() -> dict[str, Any]:
        """Hand the changed set of closed airports (the RECOVER item) to the recovery agent,
        which re-plans the airline's network in the background for a dispatcher to approve."""
        return await toolkit.run_recovery()

    async def draft_sra(region: str) -> dict[str, Any]:
        """Hand a region (the subject of an SRA item) to the SRA drafter: a draft safety risk
        assessment for a dispatcher and the safety manager to complete and sign."""
        return await toolkit.draft_sra(region)

    def defer(item_ids: list[str], reason: str) -> dict[str, Any]:
        """Leave optional items (not mandatory) for the next run, with one short reason."""
        return toolkit.defer(item_ids, reason)

    def submit_brief(
        summary: str, priority_item_ids: list[str], priority_reasons: list[str], watch: list[str]
    ) -> dict[str, Any]:
        """Finish the run with the operational brief for the dispatchers: a summary of at most
        three sentences, the item ids in the order they matter with one reason each, and up to
        four things to watch. Use only numbers and flights you were given; no clock times."""
        return toolkit.submit_brief(summary, priority_item_ids, priority_reasons, watch)

    return LlmAgent(
        name=AGENT_NAME,
        model=model,
        description="TEPHRA duty officer: orders and delegates the volcanic-ash desk's AI work.",
        instruction=_instruction,
        tools=[assess_volcanoes, plan_flights, run_recovery, draft_sra, defer, submit_brief],
        generate_content_config=types.GenerateContentConfig(temperature=temperature_for(model)),
        before_model_callback=before_model_callback,
        on_model_error_callback=on_model_error_callback,
    )


def _instruction(_: Any) -> str:
    # A provider (not a plain string) so ADK does not template "{...}" in the prompt file.
    return PROMPT_PATH.read_text(encoding="utf-8")


def _task_text(digest: str, toolkit: DutyToolkit) -> str:
    worklist = json.dumps([_item_view(item) for item in toolkit.pending()], ensure_ascii=False)
    return (
        "The desk's picture now (written by code):\n"
        f"{digest}\n\n"
        f"Work due (JSON):\n{worklist}\n\n"
        "Delegate the work in the order that protects flights first, defer only what can wait,"
        " then call submit_brief once."
    )


def _repair_text(toolkit: DutyToolkit) -> str:
    lines: list[str] = []
    if toolkit.brief_problems:
        listed = "\n".join(f"- {problem}" for problem in first_problems(toolkit.brief_problems))
        lines.append(f"Code rejected the brief:\n{listed}")
    elif toolkit.brief is None:
        lines.append("No brief was submitted.")
    mandatory = [_item_view(item) for item in toolkit.undispatched_mandatory()]
    if mandatory:
        lines.append(
            "Mandatory items are still undone; dispatch them now: "
            + json.dumps(mandatory, ensure_ascii=False)
        )
    lines.append(
        "Then call submit_brief once, with numbers and flights taken from what you were given."
    )
    return "\n".join(lines)


def _item_view(item: DutyItem) -> dict[str, Any]:
    return {
        "item_id": item.id,
        "kind": item.kind.value,
        "subject": item.subject,
        "label": item.label,
        "mandatory": item.mandatory,
        "urgency": item.urgency,
    }


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _emit_result(trace: TraceSink | None, duty: DutyRun) -> None:
    delegated = len(duty.dispatches)
    if duty.outcome == "MODEL_FAILED":
        reasons = "; ".join(first_problems(duty.validation_errors, 3)) or "NO BRIEF"
        _emit(
            trace,
            "code",
            f"Duty Officer AI UNAVAILABLE ({reasons}); {delegated} delegation(s) made, "
            f"{len(duty.undispatched)} mandatory item(s) to the Desk",
            level="error",
        )
        return
    actor: TraceActor = "stub" if duty.outcome == "STUB" else "adk"
    deferred = f", {len(duty.deferred)} deferred" if duty.deferred else ""
    _emit(trace, actor, f"Duty Officer brief: {delegated} delegation(s){deferred}")
    if duty.undispatched:
        _emit(
            trace,
            "code",
            f"Duty Officer left {len(duty.undispatched)} mandatory item(s) undone: to the Desk",
            level="error",
        )


def _emit(
    trace: TraceSink | None,
    actor: TraceActor,
    message: str,
    *,
    level: Literal["info", "warn", "error"] = "info",
) -> None:
    if trace is not None:
        trace(TraceEvent.new(TraceStage.DUTY, actor, message, level=level))
