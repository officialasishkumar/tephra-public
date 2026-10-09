"""Replay cases and the LIVE/REPLAY clock switch.

A case is ``data/replay/<case_id>/manifest.json`` (a :class:`ReplayCase`) plus the raw
responses it lists. :class:`ReplaySource` answers the feed parsers through the same
``Source`` interface as live HTTP, matching on the exact URL, so every parser runs on the
bytes the feed really served. Replayed results say ``replay=True`` and keep their recorded
fetch time and SHA-256, which is checked against the file before it is served.
"""

import asyncio
import logging
import re
from bisect import bisect_right
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from tephra.config import REPLAY_BANNER_TEMPLATE
from tephra.feeds.base import FetchError, FetchResult, Source, build_url
from tephra.models import FeedId, ReplayCase, ReplayInfo, ReplayRecord
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes

__all__ = [
    "MANIFEST_NAME",
    "ReplaySource",
    "case_path",
    "cases_dir",
    "list_cases",
    "load_case",
    "replay_banner",
    "replay_info",
    "select_case",
    "start_replay_clock",
    "stop_replay_clock",
]

logger = logging.getLogger(__name__)

MANIFEST_NAME: Final = "manifest.json"
_CASE_ID: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def cases_dir(data_dir: Path) -> Path:
    return data_dir / "replay"


def case_path(data_dir: Path, case_id: str) -> Path:
    if _CASE_ID.fullmatch(case_id) is None:
        raise ValueError(f"invalid replay case id {case_id!r}")
    return cases_dir(data_dir) / case_id


def list_cases(data_dir: Path) -> list[ReplayCase]:
    """Every readable case, newest ``recorded_from`` first; unreadable ones are logged."""
    root = cases_dir(data_dir)
    if not root.is_dir():
        return []
    cases: list[ReplayCase] = []
    for manifest in sorted(root.glob(f"*/{MANIFEST_NAME}")):
        try:
            cases.append(ReplayCase.model_validate_json(manifest.read_bytes()))
        except (OSError, ValidationError) as exc:
            logger.warning("skipping replay case %s: %s", manifest.parent.name, exc)
    return sorted(cases, key=lambda case: case.recorded_from, reverse=True)


def load_case(data_dir: Path, case_id: str) -> ReplayCase:
    manifest = case_path(data_dir, case_id) / MANIFEST_NAME
    if not manifest.is_file():
        raise FileNotFoundError(f"replay case {case_id!r} has no {MANIFEST_NAME}")
    case = ReplayCase.model_validate_json(manifest.read_bytes())
    if case.case_id != case_id:
        raise ValueError(f"manifest in {case_id!r} names case {case.case_id!r}")
    return case


def select_case(data_dir: Path, case_id: str | None) -> ReplayCase:
    """The named case, or the newest one when ``case_id`` is unset (``TEPHRA_REPLAY_CASE``)."""
    if case_id:
        return load_case(data_dir, case_id)
    cases = list_cases(data_dir)
    if not cases:
        raise FileNotFoundError(f"no replay case under {cases_dir(data_dir)}")
    return cases[0]


def replay_banner(case: ReplayCase) -> str:
    return REPLAY_BANNER_TEMPLATE.format(date=case.recorded_from.strftime("%d %b %Y"))


def replay_info(case: ReplayCase, *, auto: bool) -> ReplayInfo:
    return ReplayInfo(
        case_id=case.case_id,
        label=case.label,
        recorded_from=case.recorded_from,
        recorded_to=case.recorded_to,
        banner=replay_banner(case),
        auto=auto,
    )


def start_replay_clock(case: ReplayCase, *, speed: float) -> timeutil.ReplayClock:
    """Move every module's ``now()`` to the recording, starting at its first fetch."""
    clock = timeutil.ReplayClock(case.recorded_from, case.recorded_to, speed=speed)
    timeutil.set_clock(clock)
    return clock


def stop_replay_clock() -> None:
    timeutil.set_clock(timeutil.SystemClock())


class ReplaySource(Source):
    """Serves a case's recorded responses by exact URL.

    For a URL recorded several times, the latest record fetched at or before the replay
    clock's ``now()`` is served (the earliest one before the first recording).
    """

    def __init__(self, case_dir: Path, case: ReplayCase) -> None:
        self._case_dir = case_dir.resolve()
        self._case = case
        by_url: dict[str, list[ReplayRecord]] = {}
        for record in case.records:
            by_url.setdefault(record.url, []).append(record)
        self._records = {
            url: sorted(records, key=lambda record: record.fetched_at)
            for url, records in by_url.items()
        }
        self._verified: dict[str, bytes] = {}

    @property
    def case(self) -> ReplayCase:
        return self._case

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        records = self._records.get(full_url)
        if not records:
            raise FetchError(full_url, feed, f"not recorded in replay case {self._case.case_id}")
        record = _pick(records)
        content = await asyncio.to_thread(self._read, record, full_url, feed)
        return FetchResult(
            feed=feed,
            url=full_url,
            status_code=record.status_code,
            content=content,
            content_type=record.content_type,
            fetched_at=record.fetched_at,
            sha256=record.sha256,
            replay=True,
        )

    async def aclose(self) -> None:
        self._verified.clear()

    def _read(self, record: ReplayRecord, url: str, feed: FeedId) -> bytes:
        cached = self._verified.get(record.path)
        if cached is not None:
            return cached
        path = (self._case_dir / record.path).resolve()
        if not path.is_relative_to(self._case_dir):
            raise FetchError(url, feed, f"record path {record.path!r} leaves the case directory")
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise FetchError(url, feed, f"recorded file unreadable: {exc}") from exc
        if sha256_bytes(content) != record.sha256:
            raise FetchError(url, feed, f"recorded file {record.path} does not match its sha256")
        self._verified[record.path] = content
        return content


def _pick(records: list[ReplayRecord]) -> ReplayRecord:
    times = [record.fetched_at for record in records]
    index = bisect_right(times, timeutil.now())
    return records[index - 1] if index else records[0]
