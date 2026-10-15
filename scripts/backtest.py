"""Replay recorded cases in 30-minute steps and score TEPHRA's zone against later official areas.

Arm D (the default) uses the offline stub plume reader and touches no network and no model.
Arm G replays Gemini plume reads from the LLM disk cache and spends at most ``--max-calls``
new calls (0 by default); it needs TEPHRA_LLM=gemini and GEMINI_API_KEY. ``--report`` makes one
lite-tier Gemini call that writes ``REPORT.md`` from the scorecard; if the model fails or its
numbers do not match the scorecard there is no report ("AI UNAVAILABLE"), only the scorecard.

    uv run python scripts/backtest.py                      # every recorded case, arm D
    uv run python scripts/backtest.py --case semeru-20260923 --step-min 60
    TEPHRA_LLM=gemini GEMINI_API_KEY=... uv run python scripts/backtest.py --arm both --max-calls 40
    TEPHRA_LLM=gemini GEMINI_API_KEY=... uv run python scripts/backtest.py --report-only
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

from tephra.agents.llm import get_llm
from tephra.backtest.report import ReportUnavailable, build_report, write_report
from tephra.backtest.runner import load_scorecard, run_backtest, write_scorecard
from tephra.config import PROJECT_ROOT, Settings, get_settings
from tephra.models import ReplayCase
from tephra.replay.cases import list_cases

DEFAULT_OUT = PROJECT_ROOT / "docs" / "backtest"


def _case_ids(settings: Settings, wanted: list[str]) -> list[str]:
    """The cases to score: the named ones, else every case. A synthetic demo case is never
    scored, named or not: its products are invented."""
    known: list[ReplayCase] = sorted(list_cases(settings.data_dir), key=lambda c: c.case_id)
    synthetic = sorted(case.case_id for case in known if case.synthetic)
    if named := sorted(set(wanted) & set(synthetic)):
        raise SystemExit(f"{', '.join(named)}: synthetic demo data, never scored")
    ids = [case.case_id for case in known if not case.synthetic]
    unknown = sorted(set(wanted) - set(ids))
    if unknown:
        raise SystemExit(f"unknown replay case(s) {', '.join(unknown)}; have {', '.join(ids)}")
    return wanted or ids


async def _report(settings: Settings, out: Path) -> int:
    report_path = out / "REPORT.md"
    if settings.llm != "gemini":
        print("AI UNAVAILABLE: the report needs TEPHRA_LLM=gemini and GEMINI_API_KEY")
        return 1
    try:
        text = await build_report(load_scorecard(out / "scorecard.json"), get_llm(settings))
    except ReportUnavailable as exc:
        report_path.unlink(missing_ok=True)  # a stale report must not disagree with the scorecard
        print(f"{exc}; scorecard.json stands alone")
        return 1
    write_report(report_path, text)
    print(f"wrote {report_path}")
    return 0


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    out: Path = args.out
    if not args.report_only:
        arms = ("D", "G") if args.arm == "both" else (args.arm,)
        scorecard = await run_backtest(
            _case_ids(settings, args.case),
            settings=settings,
            arms=arms,
            step=timedelta(minutes=args.step_min),
            max_calls=args.max_calls,
        )
        write_scorecard(scorecard, out / "scorecard.json")
        for case in scorecard.cases:
            print(
                f"{case.case_id} arm {case.arm}: {len(case.ticks)} snapshots, "
                f"coverage {case.summary.coverage_mean}, gain {case.summary.coverage_gain_mean}, "
                f"floor violations {case.floor_violations}, input leaks {case.input_leaks}"
            )
        print(f"wrote {out / 'scorecard.json'}")
        if scorecard.floor_violations or scorecard.input_leaks:
            print("SELF-TEST FAILED: floor violations or input leaks are not zero")
            return 2
    if args.report or args.report_only:
        return await _report(settings, out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backtest TEPHRA's zone on the replay cases.")
    parser.add_argument("--case", action="append", default=[], help="case id (repeatable)")
    parser.add_argument("--arm", choices=["D", "G", "both"], default="D")
    parser.add_argument("--step-min", type=int, default=30)
    parser.add_argument("--max-calls", type=int, default=0, help="new Gemini calls for arm G")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report", action="store_true", help="also write REPORT.md (Gemini)")
    parser.add_argument(
        "--report-only", action="store_true", help="write REPORT.md from the scorecard"
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
