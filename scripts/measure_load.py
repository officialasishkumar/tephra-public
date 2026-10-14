"""What one visitor costs the service: the Wall payload at three replay minutes, and the
requests a page makes per minute, read from the page sources.

Plays the case offline (the counting stand-in, no model, no network) up to each ``--at``,
builds the ``/api/wall`` response as the server does and measures it raw and gzipped (the
server gzips answers above its minimum size). The requests-per-minute figures are read from
``wall.js``, ``wall/ext.js`` and ``desk.js``: each ``setInterval`` with a fetch in its callback,
and the one SSE stream each page keeps open. Prints a Markdown table for ``docs/EVALS.md``.

    uv run python scripts/measure_load.py
    uv run python scripts/measure_load.py --at 2026-09-05T10:30Z --at 2026-09-05T14:00Z
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import importlib.util
import re
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tephra.config import PROJECT_ROOT, Settings
from tephra.desk.approvals import list_advisories
from tephra.models import SseEvent, TraceEvent, WallResponse
from tephra.scheduler import run_tick
from tephra.util import timeutil

WEB = PROJECT_ROOT / "tephra" / "web"
DEFAULT_AT = (
    datetime(2026, 9, 5, 10, 30, tzinfo=UTC),
    datetime(2026, 9, 5, 14, 0, tzinfo=UTC),
    datetime(2026, 9, 5, 19, 20, tzinfo=UTC),
)
WALL_ADVISORIES = 50
_INTERVAL = re.compile(r"setInterval\((?P<body>.*?),\s*(?P<ms>[0-9][0-9_e.]*)\)", re.DOTALL)
_FETCH = re.compile(r"""fetch\(\s*[`"'](/api/[^`"'$]*)""")
_EXT_ROW = re.compile(r"""\["[a-z_]+",\s*"(/api/[a-z_/]+)""")


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


def _ms(text: str) -> float:
    return float(text.replace("_", ""))


def polling_from_source() -> list[dict[str, Any]]:
    """Each page's timers that fetch, with the fetches each timer makes per minute."""
    rows: list[dict[str, Any]] = []
    ext_rows = len(_EXT_ROW.findall((WEB / "wall" / "ext.js").read_text(encoding="utf-8")))
    for page, files in (("Wall", ("wall.js",)), ("Desk", ("desk.js",))):
        per_minute = 0.0
        timers: list[str] = []
        for name in files:
            source = (WEB / name).read_text(encoding="utf-8")
            for match in _INTERVAL.finditer(source):
                body = match.group("body")
                fetches = _FETCH.findall(body)
                if "loadExt" in body:
                    fetches = [f"{ext_rows} ext endpoints"]
                    calls = ext_rows
                else:
                    calls = len(fetches)
                if not calls:
                    continue
                every_s = _ms(match.group("ms")) / 1000
                per_minute += calls * 60 / every_s
                timers.append(f"{', '.join(fetches)} every {every_s:g} s")
        rows.append(
            {
                "page": page,
                "streams": 1,  # one EventSource on /api/events
                "polling_per_minute": round(per_minute, 1),
                "timers": timers or ["none: updates arrive on the stream"],
            }
        )
    return rows


async def wall_sizes(
    case_id: str, at_times: list[datetime], quantum_s: int
) -> list[dict[str, Any]]:
    counting = _sibling("count_model_calls")
    asks: Counter[str] = Counter()
    counting.stand_in_agents(asks)
    settings = Settings(_env_file=None, llm="stub", recovery_auto=False)
    sizes: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="tephra-load-") as name:
        runtime = counting.runtime_for(case_id, settings, counting.CountingModel(asks), Path(name))
        try:
            with timeutil.use_clock(timeutil.FixedClock(min(at_times))) as clock:
                for at in sorted(at_times):
                    clock.set(counting.floored(at, quantum_s))  # type: ignore[attr-defined]
                    await run_tick(runtime, reason="measure")
                    await runtime.worker.drain()
                    drafts = await list_advisories(runtime.store, limit=WALL_ADVISORIES)
                    response = WallResponse(
                        state=await runtime.system_state(),
                        snapshot=await runtime.wall_snapshot(),
                        advisories=drafts,
                        trace=[
                            TraceEvent.model_validate(event.data)
                            for event in runtime.bus.recent(SseEvent.TRACE, limit=100)
                        ],
                    )
                    raw = response.model_dump_json().encode()
                    sizes.append(
                        {
                            "at": timeutil.to_iso(at),
                            "raw_bytes": len(raw),
                            "gzip_bytes": len(gzip.compress(raw, compresslevel=9)),
                            "advisories": len(drafts),
                            "exposed": len(runtime.exposed),
                        }
                    )
        finally:
            await runtime.aclose()
    return sizes


def markdown(sizes: list[dict[str, Any]], polling: list[dict[str, Any]]) -> str:
    lines = [
        "| Replay minute | /api/wall raw | gzipped | advisories | flights in or heading in |",
        "|---|---|---|---|---|",
    ]
    for row in sizes:
        raw_kb, gzip_kb = row["raw_bytes"] / 1024, row["gzip_bytes"] / 1024
        lines.append(
            f"| {row['at']} | {raw_kb:.0f} KB | {gzip_kb:.0f} KB | "
            f"{row['advisories']} | {row['exposed']} |"
        )
    lines += [
        "",
        "| Page | Open streams | Polling requests per minute | Timers (from source) |",
        "|---|---|---|---|",
    ]
    for row in polling:
        lines.append(
            f"| {row['page']} | {row['streams']} | {row['polling_per_minute']:g} | "
            f"{'; '.join(row['timers'])} |"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", default="anak-krakatau-20260905")
    parser.add_argument("--at", action="append", type=_utc, help="replay minute (repeatable)")
    parser.add_argument("--quantum-s", type=int, default=60)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    at_times = args.at or list(DEFAULT_AT)
    sizes = asyncio.run(wall_sizes(args.case, at_times, args.quantum_s))
    print(markdown(sizes, polling_from_source()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
