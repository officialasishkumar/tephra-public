"""Record a labelled replay case into ``data/replay/<case_id>/``.

Two ways to fill a case, which can be combined:

``live``      Run the real pollers (stub LLM, throwaway store) for a while and keep every
              fresh response through :class:`tephra.feeds.base.RecordingSource`.
``backfill``  Rebuild a past window from archives:
              * VA SIGMETs from aviationweather.gov, which serves ``date=`` snapshots for the
                last 30 days only (research/05, research/14);
              * Darwin VAA bulletins from archived text files (for example the BoM FTP
                ``IDY4128x.YYYYMMDDHHMM.txt`` files saved under research/data/census/raw/).
              Each response is stored under the URL the live poller requests, with
              ``fetched_at`` set to the time it describes, so ``ReplaySource`` serves it as
              if it had been fetched then. The manifest's notes say it was reconstructed.

VONAs are recorded only with ``--with-vona``: MAGMA's robots.txt disallows crawling
(research/05), so use it only with PVMBG's permission.

Run it yourself (it makes network requests); nothing here is run by agents.

Examples::

    uv run python scripts/record_replay.py live --case semeru-live-20261011 \
        --label "Semeru, live feeds 11 Oct 2026" --minutes 90
    uv run python scripts/record_replay.py backfill --case semeru-20260923 \
        --label "Semeru SIGMET MOV SE vs VONA N/NE, 23-27 Sep 2026" \
        --start 2026-09-23T12:00:00Z --end 2026-09-27T06:00:00Z \
        --darwin-dir research/data/census/raw/darwin/ftp
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import re
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tephra.config import Settings
from tephra.feeds.base import HttpSource, RecordingSource, build_url
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL
from tephra.feeds.vaac import DARWIN_BULLETIN_URLS
from tephra.models import FeedId, ReplayCase, ReplayRecord, RunMode
from tephra.pipeline import create_runtime
from tephra.replay.cases import case_path
from tephra.util import timeutil

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_DARWIN_HEADER = re.compile(r"\bFVAU0([1-4])\s+ADRM\b")
_ARCHIVE_STAMP = re.compile(r"\.(\d{12})\.txt$")


def _utc(text: str) -> datetime:
    return timeutil.parse_iso(text).astimezone(UTC)


def _settings(args: argparse.Namespace, workdir: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        mode=RunMode.LIVE,
        store="sqlite",
        sqlite_path=workdir / "record.sqlite3",
        cache_dir=workdir / "cache",
        region=args.region,
        vona_live=args.with_vona,
        science=args.science,
    )


async def record_live(args: argparse.Namespace, case_dir: Path) -> list[ReplayRecord]:
    with tempfile.TemporaryDirectory(prefix="tephra-record-") as tmp:
        settings = _settings(args, Path(tmp))
        runtime = await create_runtime(settings)
        recorder = RecordingSource(runtime.source, case_dir)
        runtime.source = recorder
        deadline = asyncio.get_running_loop().time() + args.minutes * 60
        ticks = 0
        try:
            while asyncio.get_running_loop().time() < deadline:
                report = await runtime.tick(reason="record")
                ticks += 1
                print(
                    f"tick {ticks}: {len(report.feeds_polled)} feeds polled, "
                    f"{len(recorder.records)} responses recorded so far"
                )
                await asyncio.sleep(args.interval)
        finally:
            await runtime.aclose()  # also closes the recorder and the live source inside it
        return recorder.records


async def backfill_sigmets(
    start: datetime, end: datetime, step: timedelta, case_dir: Path
) -> list[ReplayRecord]:
    """One AWC ``date=`` snapshot per step, stored under the live poller's URL."""
    live_url = build_url(SIGMET_URL, SIGMET_PARAMS)
    oldest = datetime.now(UTC) - timedelta(days=30)
    if start < oldest:
        print(f"warning: AWC keeps 30 days; snapshots before {oldest:%Y-%m-%d %H:%MZ} will fail")
    source = HttpSource(cache_dir=case_dir / ".fetch-cache")
    records: list[ReplayRecord] = []
    try:
        at = start
        while at <= end:
            params = {**SIGMET_PARAMS, "date": at.strftime("%Y-%m-%dT%H:%M:%SZ")}
            try:
                result = await source.fetch(SIGMET_URL, feed=FeedId.SIGMET, params=params)
            except Exception as exc:  # one missing hour should not end the backfill
                print(f"  {at:%Y-%m-%d %H:%MZ}: failed ({exc})")
            else:
                if not result.from_cache:
                    records.append(
                        _store(
                            case_dir,
                            FeedId.SIGMET,
                            live_url,
                            at,
                            result.content,
                            result.status_code,
                            result.content_type,
                        )
                    )
                    print(f"  {at:%Y-%m-%d %H:%MZ}: {len(result.content)} bytes")
            at += step
    finally:
        await source.aclose()
    return records


def import_darwin(
    directory: Path, start: datetime, end: datetime, case_dir: Path
) -> list[ReplayRecord]:
    """Archived Darwin VAA bulletins, each stored under its tgftp FVAU0n URL."""
    records: list[ReplayRecord] = []
    for path in sorted(directory.glob("*.txt")):
        stamp = _ARCHIVE_STAMP.search(path.name)
        if not stamp:
            continue
        at = datetime.strptime(stamp.group(1), "%Y%m%d%H%M").replace(tzinfo=UTC)
        if not start <= at <= end:
            continue
        content = path.read_bytes()
        header = _DARWIN_HEADER.search(content.decode("utf-8", errors="replace"))
        if not header:
            print(f"  skipped {path.name}: no FVAU0n ADRM header")
            continue
        url = DARWIN_BULLETIN_URLS[int(header.group(1)) - 1]
        records.append(_store(case_dir, FeedId.VAAC_DARWIN, url, at, content, 200, "text/plain"))
    print(f"  imported {len(records)} Darwin bulletins from {directory}")
    return records


def _store(
    case_dir: Path,
    feed: FeedId,
    url: str,
    at: datetime,
    content: bytes,
    status_code: int,
    content_type: str | None,
) -> ReplayRecord:
    digest = hashlib.sha256(content).hexdigest()
    suffix = ".json" if (content_type or "").startswith("application/json") else ".txt"
    name = f"{timeutil.compact(at, seconds=True)}_{digest[:12]}{suffix}"
    relative = Path("raw") / feed.value / name
    target = case_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return ReplayRecord(
        feed=feed,
        url=url,
        fetched_at=at,
        sha256=digest,
        path=relative.as_posix(),
        status_code=status_code,
        content_type=content_type,
    )


def write_manifest(
    args: argparse.Namespace, case_dir: Path, records: list[ReplayRecord], notes: str
) -> Path:
    if not records:
        raise SystemExit("nothing was recorded; no manifest written")
    times = [record.fetched_at for record in records]
    case = ReplayCase(
        case_id=args.case,
        label=args.label,
        recorded_from=min(times),
        recorded_to=max(times),
        region=args.region,
        volcano_ids=args.volcano or [],
        notes=notes,
        records=sorted(records, key=lambda record: record.fetched_at),
    )
    path = case_dir / "manifest.json"
    path.write_text(case.model_dump_json(indent=2))
    return path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a labelled TEPHRA replay case.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("live", "backfill"):
        p = sub.add_parser(name)
        p.add_argument("--case", required=True, help="case id: lowercase letters, digits, dashes")
        p.add_argument("--label", required=True, help="human label shown on the REPLAY banner")
        p.add_argument("--region", default="java_bali")
        p.add_argument("--volcano", action="append", help="volcano id to tag (repeatable)")
        p.add_argument("--data-dir", type=Path, default=Path("data"))
        p.add_argument("--force", action="store_true", help="overwrite an existing case")
    live = sub.choices["live"]
    live.add_argument("--minutes", type=float, default=60.0)
    live.add_argument("--interval", type=float, default=60.0, help="seconds between ticks")
    live.add_argument(
        "--with-vona",
        action="store_true",
        help="also poll MAGMA VONAs (only with PVMBG's permission)",
    )
    live.add_argument("--science", action="store_true", help="also fetch raw Himawari segments")
    back = sub.choices["backfill"]
    back.add_argument("--start", required=True, type=_utc)
    back.add_argument("--end", required=True, type=_utc)
    back.add_argument("--step-minutes", type=int, default=60)
    back.add_argument("--darwin-dir", type=Path, help="directory of archived FVAU bulletins")
    back.add_argument("--no-sigmets", action="store_true")
    args = parser.parse_args(argv)
    if not _CASE_ID.match(args.case):
        parser.error("--case must be 3-64 chars of lowercase letters, digits and dashes")
    if args.command == "backfill" and args.end <= args.start:
        parser.error("--end must be after --start")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    case_dir = case_path(args.data_dir, args.case)
    if (case_dir / "manifest.json").exists() and not args.force:
        raise SystemExit(f"{case_dir} already has a manifest; pass --force to overwrite")
    case_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "live":
        records = asyncio.run(record_live(args, case_dir))
        notes = f"Recorded live from public feeds for {args.minutes:g} min."
    else:
        records: list[ReplayRecord] = []
        parts = []
        if not args.no_sigmets:
            records += asyncio.run(
                backfill_sigmets(
                    args.start, args.end, timedelta(minutes=args.step_minutes), case_dir
                )
            )
            parts.append(
                f"VA SIGMETs from aviationweather.gov date= snapshots every {args.step_minutes} min"
            )
        if args.darwin_dir:
            records += import_darwin(args.darwin_dir, args.start, args.end, case_dir)
            parts.append(f"Darwin VAA bulletins imported from archive files ({args.darwin_dir})")
        notes = (
            "Reconstructed from archives, not recorded live: " + "; ".join(parts) + ". Each "
            "response is stored under the live poller's URL at the time it describes."
        )
    path = write_manifest(args, case_dir, records, notes)
    print(f"wrote {path} ({len(records)} responses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
