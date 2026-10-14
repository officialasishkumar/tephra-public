"""Replay metrics for the Track record: how long a flight waits for its draft, and the tokens.

Plays the window offline (the stub's answers through the counting stand-in, as
``count_model_calls.py`` does) and reads the reasoning trace: for each flight, the replay
minutes from its first EXPOSURE line to its first DESK "DRAFT ... waiting for a dispatcher"
line. The median and p90 are labelled "stub, replay clock, model latency excluded": the stub
answers at once, so a live run adds the models' latency. With ``--store`` the token fields of
the advisories, Coordinator runs, Ask answers and recovery plans in that store are summed; a
figure that no record carries reads "not measured". Writes ``docs/evals/replay-metrics.json``.

    uv run python scripts/replay_metrics.py --start 2026-09-05T10:30:00Z --minutes 60
    uv run python scripts/replay_metrics.py --store .state/tephra.sqlite3
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import statistics
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from tephra.config import PROJECT_ROOT, Settings
from tephra.models import SseEvent, TraceEvent, TraceStage
from tephra.scheduler import run_tick
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil

OUT_PATH = PROJECT_ROOT / "docs" / "evals" / "replay-metrics.json"
SPEED_LABEL = "stub, replay clock, model latency excluded"
NOT_MEASURED = "not measured"
TOKEN_COLLECTIONS = (
    Collection.ADVISORIES,
    Collection.DUTY,
    Collection.ASK_LOG,
    Collection.RECOVERY,
)
DRAFT_WAITING = "waiting for a dispatcher"


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


def waits_from_trace(events: list[TraceEvent]) -> dict[str, float]:
    """Flight id -> replay minutes from its first EXPOSURE line to its first draft line."""
    exposed: dict[str, datetime] = {}
    drafted: dict[str, datetime] = {}
    for event in events:
        if event.flight_id is None:
            continue
        if event.stage is TraceStage.EXPOSURE:
            exposed.setdefault(event.flight_id, event.at)
        elif event.stage is TraceStage.DESK and DRAFT_WAITING in event.message:
            drafted.setdefault(event.flight_id, event.at)
    return {
        flight_id: (drafted[flight_id] - at).total_seconds() / 60
        for flight_id, at in exposed.items()
        if flight_id in drafted and drafted[flight_id] >= at
    }


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))]


async def play(args: argparse.Namespace) -> tuple[list[TraceEvent], Counter[str]]:
    counting = _sibling("count_model_calls")
    asks: Counter[str] = Counter()
    counting.stand_in_agents(asks)
    settings = Settings(_env_file=None, llm="stub", recovery_auto=False)
    events: list[TraceEvent] = []
    with tempfile.TemporaryDirectory(prefix="tephra-metrics-") as name:
        runtime = counting.runtime_for(
            args.case, settings, counting.CountingModel(asks), Path(name)
        )
        subscription = runtime.bus.subscribe(maxsize=100_000)
        try:
            with timeutil.use_clock(timeutil.FixedClock(args.start)) as clock:
                for minute in range(args.minutes):
                    at = counting.floored(args.start + timedelta(minutes=minute), args.quantum_s)
                    clock.set(at)  # type: ignore[attr-defined]
                    await run_tick(runtime, reason="metrics")
                    await runtime.worker.drain()
                    while (event := await subscription.get(within_s=0.01)) is not None:
                        if event.name == SseEvent.TRACE:
                            events.append(TraceEvent.model_validate(event.data))
        finally:
            subscription.close()
            await runtime.aclose()
    return events, asks


async def token_sums(path: Path) -> dict[str, Any]:
    store = SqliteStore(path, path.parent / "blobs")
    sums: dict[str, Any] = {}
    try:
        for collection in TOKEN_COLLECTIONS:
            docs = await store.list_docs(collection, limit=100_000)
            metered = [
                doc
                for doc in docs
                if doc.get("input_tokens") is not None or doc.get("output_tokens") is not None
            ]
            sums[collection.value] = (
                {
                    "records": len(docs),
                    "metered": len(metered),
                    "input_tokens": sum(int(doc.get("input_tokens") or 0) for doc in metered),
                    "output_tokens": sum(int(doc.get("output_tokens") or 0) for doc in metered),
                }
                if metered
                else NOT_MEASURED
            )
    finally:
        await store.aclose()
    return sums


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="anak-krakatau-20260905")
    parser.add_argument("--start", type=_utc, default=datetime(2026, 9, 5, 10, 30, tzinfo=UTC))
    parser.add_argument("--minutes", type=int, default=60)
    parser.add_argument("--quantum-s", type=int, default=60)
    parser.add_argument("--store", type=Path, help="SQLite store whose token fields are summed")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    events, asks = asyncio.run(play(args))
    waits = waits_from_trace(events)
    minutes = list(waits.values())
    speed: dict[str, Any] = {
        "label": SPEED_LABEL,
        "case": args.case,
        "window_from": timeutil.to_iso(args.start),
        "window_minutes": args.minutes,
        "flights_exposed": sum(
            1 for event in events if event.stage is TraceStage.EXPOSURE and event.flight_id
        ),
        "flights_drafted": len(waits),
        "median_minutes": round(statistics.median(minutes), 1) if minutes else NOT_MEASURED,
        "p90_minutes": round(_p90(minutes), 1) if minutes else NOT_MEASURED,
        "stand_in_asks": dict(sorted(asks.items())),
    }
    tokens = asyncio.run(token_sums(args.store)) if args.store else NOT_MEASURED
    result = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "speed": speed,
        "tokens": tokens,
        "note": "Speed is measured on the replay clock with the stub's instant answers; a live "
        "run adds the models' latency. Tokens come from records that carry token fields; "
        "'not measured' where none does.",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
