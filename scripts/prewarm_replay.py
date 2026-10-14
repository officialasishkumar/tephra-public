"""Fill a replay case's answer store ahead of time, and export it as the case's seed.

The demo replay asks its models the same material questions on every loop; an answer that
passed the code's checks is kept (``ai_answers``) and found again at zero quota. This script
plays the window once or twice with the real backend (``TEPHRA_LLM=gemini``) against a store of
its own, so the answers exist before anyone watches. It is the count script's loop
(``count_model_calls.py``) with the real models; every call is counted against the same free
budget the service uses, so it **refuses to start** unless ``--service-budget-paused`` says the
service's main budget is paused for the day (``TEPHRA_MODEL_DAILY_BUDGET=0`` on the service) or
the store is the production Firestore (the service's own, so nothing is asked twice).

It stops with exit code 3 when a model's day is exhausted with work left; the next run with the
same ``--store`` resumes, because every answer kept so far is found again. ``--export <dir>``
writes ``ai_answers.jsonl`` (one kept answer a line, as stored) and ``answers.json`` (the window,
the build, the model ids, the prompt versions and the counts) for ``data/replay/<case>/answers/``,
which a REPLAY run loads on restore and re-checks before use. Stub answers (``TEPHRA_LLM=stub``,
or the counting stand-in) are never exported unless ``--allow-stub-export`` (tests only).
``--export-from-store firestore`` exports from the production store without a fill (the owner's
gcloud context; agents never run it).

    TEPHRA_LLM=gemini GEMINI_API_KEY=... uv run python scripts/prewarm_replay.py \\
        --case anak-krakatau-20260905 --start 2026-09-05T10:30:00Z --minutes 540 --loops 2 \\
        --quantum-s 60 --store .state/prewarm-anak-krakatau-20260905.sqlite3 \\
        --export data/replay/anak-krakatau-20260905/answers --service-budget-paused
    TEPHRA_STORE=firestore TEPHRA_GCP_PROJECT=... TEPHRA_GCS_BUCKET=... uv run python \\
        scripts/prewarm_replay.py --case anak-krakatau-20260905 --export-from-store firestore \\
        --export data/replay/anak-krakatau-20260905/answers
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tephra.agents.answers import AiAnswer, prompt_version
from tephra.agents.llm import get_llm
from tephra.agents.quota import QuotaLedger
from tephra.config import PROJECT_ROOT, Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import RunMode
from tephra.pipeline import Runtime
from tephra.policy import load_policy
from tephra.replay.cases import ReplaySource, case_path, load_case
from tephra.scheduler import run_tick
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.events import EventBus

EXIT_REFUSED = 2
EXIT_BUDGET_EXHAUSTED = 3
PROMPTS_DIR = PROJECT_ROOT / "tephra" / "agents" / "prompts"
STUB_MODEL_IDS = frozenset({"stub", "none"})
ANSWERS_NOTE = (
    "Answers the models named here gave to this case's material questions, kept because they "
    "passed the code's checks; a REPLAY run loads them on restore and checks each again before "
    "use. Lines are ai_answers documents as stored."
)


def _sibling(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def prewarm_settings(args: argparse.Namespace) -> Settings:
    if args.store == "firestore":
        return Settings(_env_file=None, store="firestore", recovery_auto=False)
    path = Path(args.store)
    return Settings(
        _env_file=None,
        store="sqlite",
        sqlite_path=path,
        cache_dir=path.parent / f"{path.stem}-cache",
        recovery_auto=False,
    )


def runtime_for(
    case_id: str, settings: Settings, store: Store, llm: Any, ledger: QuotaLedger
) -> Runtime:
    case = load_case(settings.data_dir, case_id)
    policy = load_policy(settings.data_dir)
    runtime = Runtime(
        settings=settings,
        store=store,
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
        ledger=ledger,
    )
    runtime.worker.paced = False  # the budget caps the work; pacing would only slow the fill
    return runtime


async def exhausted(runtime: Runtime) -> str | None:
    """The first model whose day is closed or spent, or None."""
    view = await runtime.budget_view()
    for model in view.models:
        if model.closed or model.remaining <= 0:
            return model.model_id
    return None


async def fill(args: argparse.Namespace, settings: Settings) -> dict[str, Any]:
    counting = _sibling("count_model_calls")
    asks: Counter[str] = Counter()
    store = open_store(settings)
    ledger = QuotaLedger(settings, store)
    if settings.llm == "stub":
        counting.stand_in_agents(asks)
        llm: Any = counting.CountingModel(asks)
    else:
        llm = get_llm(settings, quota=ledger)
    runtime = runtime_for(args.case, settings, store, llm, ledger)
    result: dict[str, Any] = {
        "case": args.case,
        "backend": llm.name,
        "start": timeutil.to_iso(args.start),
        "minutes": args.minutes,
        "loops": args.loops,
        "quantum_s": args.quantum_s,
        "status": "filled",
    }
    try:
        with timeutil.use_clock(timeutil.FixedClock(args.start)) as clock:
            for loop in range(args.loops):
                for minute in range(args.minutes):
                    at = counting.floored(args.start + timedelta(minutes=minute), args.quantum_s)
                    clock.set(at)  # type: ignore[attr-defined]
                    await run_tick(runtime, reason="prewarm")
                    await runtime.worker.drain()
                    # The stub spends no quota (its stand-in model ids have no budget row).
                    spent = None if settings.llm == "stub" else await exhausted(runtime)
                    if spent is not None:
                        left = (args.loops - loop) * args.minutes - minute - 1
                        result.update(
                            status="budget_exhausted",
                            model_id=spent,
                            stopped_at=timeutil.to_iso(at),
                            minutes_left=left,
                        )
                        break
                if result["status"] != "filled":
                    break
        book = getattr(runtime, "_answer_book", None)
        result["answers"] = (
            {f"{skill} {outcome}": n for (skill, outcome), n in sorted(book.counts.items())}
            if book is not None
            else {}
        )
        days = await ledger.load_all([settings.model, settings.model_lite])
        result["calls_today"] = {day.model_id: day.total for day in days}
        result["stand_in_asks"] = dict(sorted(asks.items()))
    finally:
        await runtime.aclose()
    return result


def is_stub_answer(doc: dict[str, Any]) -> bool:
    model_id = str(doc.get("model_id") or "")
    return (
        model_id in STUB_MODEL_IDS
        or model_id.startswith("counting-")
        or doc.get("llm_backend") == "stub"
    )


async def export(
    store: Store, case_id: str, out_dir: Path, settings: Settings, *, allow_stub: bool
) -> dict[str, Any]:
    docs = await store.list_docs(
        Collection.AI_ANSWERS, limit=100_000, order_by="stored_at", descending=False
    )
    kept = [
        doc
        for doc in docs
        if doc.get("mode") == RunMode.REPLAY.value and doc.get("case_id") == case_id
    ]
    stub = [doc for doc in kept if is_stub_answer(doc)]
    if stub and not allow_stub:
        raise SystemExit(
            f"refusing to export {len(stub)} stub answers (model ids "
            f"{sorted({doc.get('model_id') for doc in stub})}): a seed holds a model's answers only"
        )
    answers = [AiAnswer.model_validate(doc) for doc in kept]
    summary = export_summary(answers, case_id, settings)
    await asyncio.to_thread(write_export, out_dir, answers, summary)
    return summary


def export_summary(answers: list[AiAnswer], case_id: str, settings: Settings) -> dict[str, Any]:
    stored = [answer.stored_at for answer in answers]
    summary = {
        "case_id": case_id,
        "recorded_wall_from": timeutil.to_iso(min(stored)) if stored else None,
        "recorded_wall_to": timeutil.to_iso(max(stored)) if stored else None,
        "build": settings.build_sha or "local",
        "models": {"main": settings.model, "lite": settings.model_lite},
        "model_ids": sorted({answer.model_id for answer in answers}),
        "prompt_versions": {
            path.stem: prompt_version(path.read_text(encoding="utf-8"))
            for path in sorted(PROMPTS_DIR.glob("*.md"))
        },
        "counts": dict(sorted(Counter(answer.skill for answer in answers).items())),
        "note": ANSWERS_NOTE,
    }
    return summary


def write_export(out_dir: Path, answers: list[AiAnswer], summary: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "ai_answers.jsonl").open("w", encoding="utf-8") as handle:
        for answer in answers:
            handle.write(answer.model_dump_json() + "\n")
    (out_dir / "answers.json").write_text(json.dumps(summary, indent=1) + "\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="anak-krakatau-20260905")
    parser.add_argument("--start", type=_utc, default=datetime(2026, 9, 5, 10, 30, tzinfo=UTC))
    parser.add_argument("--minutes", type=int, default=540)
    parser.add_argument("--loops", type=int, default=2)
    parser.add_argument("--quantum-s", type=int, default=60, help="the replay minute, in seconds")
    parser.add_argument(
        "--store",
        default=None,
        help="SQLite file for the fill (default .state/prewarm-<case>.sqlite3), or 'firestore'",
    )
    parser.add_argument("--export", type=Path, help="write ai_answers.jsonl and answers.json here")
    parser.add_argument(
        "--export-from-store",
        choices=("sqlite", "firestore"),
        help="export only, from this store (firestore: the production store), no fill",
    )
    parser.add_argument(
        "--service-budget-paused",
        action="store_true",
        help="the service's main budget is paused today (TEPHRA_MODEL_DAILY_BUDGET=0)",
    )
    parser.add_argument("--allow-stub-export", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.store is None:
        args.store = (
            "firestore"
            if args.export_from_store == "firestore"
            else str(PROJECT_ROOT / ".state" / f"prewarm-{args.case}.sqlite3")
        )
    if args.export_from_store == "firestore":
        args.store = "firestore"
    if args.export_from_store and args.export is None:
        parser.error("--export-from-store needs --export <dir>")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = prewarm_settings(args)
    if args.export_from_store is None:
        if not args.service_budget_paused and settings.store != "firestore":
            print(
                "refusing to fill: the service spends the same budget. Pass "
                "--service-budget-paused once TEPHRA_MODEL_DAILY_BUDGET=0 is set on the service "
                "for the day, or fill the production store (--store firestore).",
                file=sys.stderr,
            )
            return EXIT_REFUSED
        result = asyncio.run(fill(args, settings))
        print(json.dumps(result, indent=1))
        if result["status"] == "budget_exhausted":
            print(
                f"budget exhausted for {result['model_id']} at {result['stopped_at']} with "
                f"{result['minutes_left']} replay minutes left; run again with the same --store",
                file=sys.stderr,
            )
            return EXIT_BUDGET_EXHAUSTED
    if args.export is not None:
        store = open_store(settings)
        try:
            summary = asyncio.run(
                export(store, args.case, args.export, settings, allow_stub=args.allow_stub_export)
            )
        finally:
            asyncio.run(store.aclose())
        print(
            f"wrote {args.export / 'ai_answers.jsonl'} ({sum(summary['counts'].values())} answers)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
