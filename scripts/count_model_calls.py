"""Count the model asks one replay window makes, per skill, with no model and no network.

A counting stand-in takes the model's place: it answers every structured call with the skill's
own offline answer (the same one ``TEPHRA_LLM=stub`` gives) under a model's name, so the code
treats it as a model (budgets, checks, answers kept and reused). The two ADK agents (the Flight
planner and the Coordinator) are replaced the same way: the planner's stand-in submits the
rule-based decision, the Coordinator's delegates the work in urgency order with a brief that
passes the checks. Each stand-in run counts as one ask (a real ADK run takes several turns).

The window plays ``--loops`` times from ``--start`` for ``--minutes`` replay minutes, one tick a
minute with the AI worker drained after each, as a looping replay plays it again. A served
replay's ticks follow the wall clock, so a later loop rarely ticks on the same seconds:
``--loop-offset-s`` starts each later loop that many seconds later than the one before.
``--quantum-s`` floors every tick instant to that many seconds, as the replay minute
(``TEPHRA_REPLAY_QUANTUM_S``) floors the clock, so an offset loop asks at the same instants.

    uv run python scripts/count_model_calls.py
    uv run python scripts/count_model_calls.py --start 2026-09-05T12:00:00Z --minutes 30 --loops 2
    uv run python scripts/count_model_calls.py --loop-offset-s 30
    uv run python scripts/count_model_calls.py --loop-offset-s 30 --quantum-s 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from tephra.agents import duty_officer, exposure_planner
from tephra.agents.llm import LlmCall, StubBackend, Tier, prompt_hash
from tephra.config import Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import DutyItemKind, LlmBackendName, RunMode
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.replay.cases import ReplaySource, case_path, load_case
from tephra.scheduler import run_tick
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.events import EventBus

SKILL_OF_SCHEMA = {
    "PlumeEstimate": "plume_reader",
    "SatelliteExtraction": "satellite_reader",
    "DraftText": "drafter",
    "SraNarrative": "sra",
    "TemplateSet": "messages",
    "Narrative": "handover",
    "NoticeExtraction": "notice_reader",
}


class CountingModel(StubBackend):
    """The stub's offline answers under a model's name; every ask is counted per skill."""

    def __init__(self, asks: Counter[str]) -> None:
        self.asks = asks

    @property
    def name(self) -> LlmBackendName:
        return "gemini"

    def model_id(self, tier: Tier) -> str:
        return f"counting-{tier}"

    async def structured[T: BaseModel](
        self,
        *,
        tier: Tier,
        system: str,
        parts: Sequence[Any],
        schema: type[T],
        stub: Callable[[], T],
        temperature: float | None = None,
    ) -> tuple[T | None, LlmCall]:
        self.asks[SKILL_OF_SCHEMA.get(schema.__name__, schema.__name__)] += 1
        value = schema.model_validate(stub().model_dump())
        call = LlmCall(
            backend="gemini",
            model_id=self.model_id(tier),
            prompt_hash=prompt_hash(system, parts),
            raw_text=value.model_dump_json(),
        )
        return value, call


def stand_in_agents(asks: Counter[str]) -> None:
    async def planner(ctx: Any, llm: Any, run: Any, **_: Any) -> None:
        asks["flight_planner"] += 1
        run.decision = exposure_planner.rule_based_decision(ctx)

    async def coordinator(toolkit: Any, llm: Any, run: Any, task: str, settings: Any) -> None:
        asks["coordinator"] += 1
        await toolkit.assess_volcanoes([i.subject for i in toolkit.pending(DutyItemKind.ASSESS)])
        await toolkit.plan_flights([i.subject for i in toolkit.pending(DutyItemKind.PLAN)])
        if toolkit.pending(DutyItemKind.RECOVER):
            await toolkit.run_recovery()
        for item in toolkit.pending(DutyItemKind.SRA):
            await toolkit.draft_sra(item.subject)
        order = sorted(toolkit.worklist(), key=lambda item: item.urgency)
        toolkit.submit_brief(
            "The work was handed out, the most urgent first.",
            [item.id for item in order],
            ["Most urgent first." for _ in order],
            [],
        )

    exposure_planner._run_agent = planner  # type: ignore[assignment]
    duty_officer._run_agent = coordinator  # type: ignore[assignment]


def runtime_for(case_id: str, settings: Settings, llm: CountingModel, work: Path) -> Runtime:
    case = load_case(settings.data_dir, case_id)
    policy = load_policy(settings.data_dir)
    runtime = Runtime(
        settings=settings,
        store=SqliteStore(work / "count.sqlite3", work / "blobs"),
        bus=EventBus(),
        source=ReplaySource(case_path(settings.data_dir, case.case_id), case),
        llm=llm,
        catalogue=load_volcanoes(settings.data_dir),
        airports=load_airports(
            settings.data_dir, min_runway_m=policy.alternates.min_runway_m.value
        ),
        routes=load_routes(settings.data_dir),
        policy=policy,
        mode=RunMode.REPLAY,
        replay_case=case,
        auto_replay=False,
    )
    runtime.worker.paced = False  # every minute's AI work runs before the next tick
    return runtime


def floored(at: datetime, quantum_s: int) -> datetime:
    """``at`` floored to the quantum, anchored to the wall clock's own boundaries as
    ``ReplayClock`` anchors it."""
    if quantum_s <= 0:
        return at
    seconds = at.timestamp()
    return datetime.fromtimestamp(seconds - seconds % quantum_s, tz=UTC)


async def count(args: argparse.Namespace) -> dict[str, Any]:
    asks: Counter[str] = Counter()
    stand_in_agents(asks)
    # Read with getattr: tests build the Namespace by hand, without every flag.
    quantum_s = int(getattr(args, "quantum_s", 0))
    settings = Settings(_env_file=None, llm="stub", recovery_auto=False)
    loops: list[dict[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="tephra-count-") as name:
        runtime = runtime_for(args.case, settings, CountingModel(asks), Path(name))
        try:
            with timeutil.use_clock(timeutil.FixedClock(args.start)) as clock:
                for loop in range(args.loops):
                    before = Counter(asks)
                    start = args.start + timedelta(seconds=loop * args.loop_offset_s)
                    for minute in range(args.minutes):
                        at = floored(start + timedelta(minutes=minute), quantum_s)
                        clock.set(at)  # type: ignore[attr-defined]
                        await run_tick(runtime, reason="count")
                        await runtime.worker.drain()
                    loops.append(dict(sorted((asks - before).items())))
            book = getattr(runtime, "_answer_book", None)
            reuse = (
                {f"{skill} {outcome}": n for (skill, outcome), n in sorted(book.counts.items())}
                if book is not None
                else None
            )
        finally:
            await runtime.aclose()
    return {
        "case": args.case,
        "start": timeutil.to_iso(args.start),
        "minutes": args.minutes,
        "loop_offset_s": args.loop_offset_s,
        "quantum_s": quantum_s,
        "loops": loops,
        "total": dict(sorted(asks.items())),
        "total_asks": sum(asks.values()),
        "answers": reuse,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="anak-krakatau-20260905")
    parser.add_argument(
        "--start",
        type=lambda text: datetime.fromisoformat(text).astimezone(UTC),
        default=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
    )
    parser.add_argument("--minutes", type=int, default=30)
    parser.add_argument("--loops", type=int, default=2)
    parser.add_argument("--loop-offset-s", type=int, default=0)
    parser.add_argument("--quantum-s", type=int, default=0, help="the replay minute, in seconds")
    print(json.dumps(asyncio.run(count(parser.parse_args())), indent=1))


if __name__ == "__main__":
    main()
