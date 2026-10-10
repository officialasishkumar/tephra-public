"""Record a labelled replay case into ``data/replay/<case_id>/``.

Every response in a case is stored under the exact URL the live poller requests, at the time
it describes, so ``ReplaySource`` serves it as if it had been fetched then. Commands:

``live``      Run the real pollers (stub LLM, throwaway store) for a while and keep every
              fresh response through :class:`tephra.feeds.base.RecordingSource`.
``noaaport``  Stream IEM NOAAPort day files (public domain; ~300 MB each, read as a stream and
              never written to disk) and keep the VA SIGMET and VAA bulletins, and the
              South-East Asian METAR and TAF collectives, as JSON lines.
``backfill``  Rebuild a past window from archives:
              * VA SIGMETs (``--sigmet-source``): aviationweather.gov ``date=`` snapshots (30
                days of history), the research census's hourly snapshots, or NOAAPort
                bulletins wrapped in the AWC isigmet JSON fields the parser reads (a
                reconstruction, and the manifest says so);
              * Darwin VAAs (``--noaaport-dir``): NOAAPort FVAU bulletins, each under the
                tgftp slot it was issued on, with every slot's last bulletin before the window
                (older advisories the relay re-sends later are skipped);
              * VONAs (``--with-vona``): the MAGMA list pages the census saved;
              * context feeds (``--context``): replay ticks over the window, through a source
                that logs every URL the pollers ask for, find the exact TAF, METAR, winds and
                ADS-B URLs. Each is filled from AWC ``date=`` history (TAF, METAR), IEM ASOS
                text converted to AWC JSON (``--metar-source iem``), the Open-Meteo
                Historical Forecast API (winds) or adsb.lol globe_history heatmaps (ADS-B,
                ``--adsb-span``), and probing repeats until nothing is missing.
``probe``     Replay ticks at chosen times: active volcanoes, discrepancies, cones, exposed
              flights, drafts, and any URL the case lacks.

Licence rule: nothing from ftp.bom.gov.au goes into a case. BoM's anonymous FTP terms say
"you may not supply that material to any other person", so Darwin VAAs come from the
public-domain NOAAPort relay. VONAs are never fetched from MAGMA here: its robots.txt
disallows crawling (research/05). ``live --with-vona`` polls MAGMA and is only for use with
PVMBG's permission.

Run it yourself: it makes network requests unless every source is an archive on disk.
``data/replay/README.md`` has the exact commands that built each case.

Examples::

    uv run python scripts/record_replay.py live --case semeru-live-20261011 \
        --label "Semeru, live feeds 11 Oct 2026" --minutes 90
    uv run python scripts/record_replay.py noaaport --day 2026-09-05 --day 2026-09-06 \
        --out /tmp/noaaport
    uv run python scripts/record_replay.py backfill --case anak-krakatau-20260905 \
        --label "Anak Krakatau closes Jakarta, 5-7 Sep 2026 (reconstructed)" \
        --start 2026-09-05T06:00Z --end 2026-09-07T06:00Z --volcano 262000 \
        --sigmet-source noaaport --noaaport-dir /tmp/noaaport \
        --census-dir research/data/census --with-vona \
        --context metar,winds,adsb --metar-source iem \
        --adsb-span 2026-09-05T10:00Z/2026-09-05T19:30Z
    uv run python scripts/record_replay.py probe --case anak-krakatau-20260905 \
        --at 2026-09-05T17:30Z --at 2026-09-06T01:00Z
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import hashlib
import io
import json
import logging
import re
import shutil
import sys
import tarfile
import tempfile
import time
from collections.abc import AsyncIterator, Callable, Hashable, Iterable, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any, BinaryIO, Final
from urllib.parse import parse_qsl, urlencode, urlsplit

import httpx
import numpy as np

from tephra.config import PROJECT_ROOT, Settings
from tephra.desk.approvals import list_advisories
from tephra.feeds.base import (
    RETRYABLE_STATUS,
    USER_AGENT,
    FetchError,
    FetchResult,
    RecordingSource,
    build_url,
)
from tephra.feeds.sigmet import SIGMET_PARAMS, SIGMET_URL
from tephra.feeds.vaac import DARWIN_BULLETIN_URLS
from tephra.feeds.vona import VONA_LIST_URL
from tephra.geo.units import distance_nm, initial_bearing_deg
from tephra.models import AdvisoryStatus, FeedId, ReplayCase, ReplayRecord, RunMode
from tephra.pipeline import Runtime, create_runtime
from tephra.replay.cases import ReplaySource, case_path, load_case
from tephra.scheduler import FEED_LABELS
from tephra.util import timeutil

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
_SNAPSHOT_DATE = re.compile(r"[?&]date=(\d{8})_(\d{4})\b")
_VONA_PAGE = re.compile(r"^https://magma\.esdm\.go\.id/v1/vona(?:\?page=(\d+))?$")
_BOM_COPYRIGHT = b"Copyright Commonwealth of Australia"
"""The footer on every BoM FTP product; such content may not be supplied to others."""
JSON_TYPE: Final = "application/json; charset=utf-8"
AWC_HISTORY_DAYS: Final = 30
DEFAULT_FIRS: Final = ("WIIF", "WAAF", "YMMM")
CONTEXT_FEEDS: Final = (FeedId.TAF, FeedId.METAR, FeedId.WINDS, FeedId.ADSB)
MAX_PROBE_ROUNDS: Final = 5


@dataclass(frozen=True)
class Saved:
    """One row of the research census's ``manifest.tsv``."""

    fetched_at: datetime
    status: int
    url: str
    path: Path
    sha256: str

    def content(self) -> bytes:
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.sha256:
            raise SystemExit(f"{self.path} does not match the sha256 in the census manifest")
        return data


def _utc(text: str) -> datetime:
    return timeutil.parse_iso(text).astimezone(UTC)


def _day(text: str) -> date:
    return date.fromisoformat(text)


def _span(text: str) -> tuple[datetime, datetime]:
    start, sep, end = text.partition("/")
    if not sep:
        raise argparse.ArgumentTypeError("a span is START/END, e.g. 2026-09-05T10:00Z/...")
    first, last = _utc(start), _utc(end)
    if last <= first:
        raise argparse.ArgumentTypeError(f"span {text} ends before it starts")
    return first, last


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


# --- polite archive GETs -------------------------------------------------------------------

_HOST_INTERVAL_S: Final = {
    "aviationweather.gov": 0.7,
    "mesonet.agron.iastate.edu": 1.5,
    "historical-forecast-api.open-meteo.com": 0.25,
    "adsb.lol": 1.0,
}
"""AWC allows 100 requests a minute; IEM throttles to one a second per IP."""
_ATTEMPTS: Final = 4


class ArchiveFetcher:
    """GETs for a backfill: a descriptive User-Agent, a pause between calls to one host,
    retries on 429 and 5xx, and (with a cache directory) a copy of every answer on disk, so
    a rebuild never fetches the same URL twice."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(120.0, connect=20.0),
            follow_redirects=True,
        )
        self._cache_dir = cache_dir / "http" if cache_dir else None
        self._ready_at: dict[str, float] = {}
        self.bytes_fetched = 0

    def close(self) -> None:
        self._client.close()

    def get(self, url: str, *, cache: bool = True) -> tuple[int, bytes]:
        """``(status, body)`` for a 200 or 204 answer; RuntimeError once retries run out."""
        cached = self._load(url) if cache else None
        if cached is not None:
            return cached
        host = urlsplit(url).hostname or ""
        reason = "not attempted"
        for attempt in range(_ATTEMPTS):
            if attempt:
                time.sleep(2.0**attempt)
            delay = self._ready_at.get(host, 0.0) - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            try:
                response = self._client.get(url)
            except httpx.HTTPError as exc:
                reason = f"{type(exc).__name__}: {exc}"
                continue
            finally:
                self._ready_at[host] = time.monotonic() + _HOST_INTERVAL_S.get(host, 0.5)
            self.bytes_fetched += response.num_bytes_downloaded
            if response.status_code in (200, 204):
                if cache:
                    self._save(url, response.status_code, response.content)
                return response.status_code, response.content
            reason = f"HTTP {response.status_code}"
            if response.status_code not in RETRYABLE_STATUS:
                break
        raise RuntimeError(f"GET {url} failed: {reason}")

    def head_size(self, url: str) -> int | None:
        response = self._client.head(url)
        if response.status_code != 200:
            return None
        return int(response.headers.get("content-length") or 0)

    def _paths(self, url: str) -> tuple[Path, Path] | None:
        if self._cache_dir is None:
            return None
        key = hashlib.sha256(url.encode()).hexdigest()[:32]
        return self._cache_dir / f"{key}.body", self._cache_dir / f"{key}.json"

    def _load(self, url: str) -> tuple[int, bytes] | None:
        paths = self._paths(url)
        if paths is None or not paths[1].is_file():
            return None
        meta = json.loads(paths[1].read_text())
        return (int(meta["status"]), paths[0].read_bytes()) if meta.get("url") == url else None

    def _save(self, url: str, status: int, content: bytes) -> None:
        paths = self._paths(url)
        if paths is None:
            return
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        paths[0].write_bytes(content)
        paths[1].write_text(json.dumps({"url": url, "status": status}))


# --- IEM NOAAPort archive -----------------------------------------------------------------

NOAAPORT_DAY_URL: Final = (
    "https://mesonet-longterm.agron.iastate.edu/archive/raw/noaaport/{day:%Y}/{day:%Y%m%d}.tgz"
)
_SOH: Final = "\x01"
_ETX: Final = "\x03"
_READ_CHUNK: Final = 8 << 20
_WMO_HEADING = re.compile(r"^[A-Z]{4}(?:\d{2})? [A-Z]{4} \d{6}(?: [A-Z]{3})?[ \t]*$", re.MULTILINE)
_HEADING_WINDOW: Final = 160
"""The heading sits on the first lines of a product, after NOAAPort's sequence number."""
_MEMBER_HOUR = re.compile(r"(\d{10})\.txt$")
_VA_SIGMET_TEXT = re.compile(r"\bVA\s+(?:ERUPTION|CLD)\b")
_ARCHIVE_SILENCE: Final = timedelta(hours=1)


@dataclass(frozen=True)
class Bulletin:
    """One WMO bulletin from the NOAAPort stream: the heading line first, LF line endings."""

    heading: str
    text: str
    hour: datetime
    """Start of the archive hour (the tar member) the bulletin arrived in."""
    order: int
    """Arrival order within its day file."""

    @property
    def cccc(self) -> str:
        return self.heading.split()[1]

    @property
    def issued_at(self) -> datetime:
        return timeutil.parse_ddhhmm(self.heading.split()[2], self.hour)

    @property
    def received_at(self) -> datetime:
        """The heading time, or the start of the hour it arrived in if that is later."""
        return max(self.issued_at, self.hour)

    def body(self) -> str:
        """The text after the heading, on one line."""
        return " ".join(self.text.partition("\n")[2].split())


def keep_bulletin(heading: str, text: str) -> bool:
    """VA SIGMETs (WV, or WS when the text is a VA SIGMET) and VAAs (FV) from every centre,
    and the METAR and TAF collectives of South-East Asian centres (``W...``)."""
    tt, cccc = heading[:2], heading.split()[1]
    if tt in ("WV", "FV"):
        return True
    if tt == "WS":
        return _VA_SIGMET_TEXT.search(text) is not None
    return tt in ("SA", "SP", "FT", "FC") and cccc.startswith("W")


def iter_products(
    stream: BinaryIO, *, last_hour: datetime | None = None
) -> Iterator[tuple[datetime, str]]:
    """``(archive hour, product text)`` for each product in an IEM NOAAPort day tarball.

    The tarball is read as a stream, one hourly member at a time and in 8 MB chunks, so a
    300 MB day never sits on disk or in memory. Products are framed by SOH and ETX.
    """
    with tarfile.open(fileobj=stream, mode="r|gz") as tar:
        for member in tar:
            match = _MEMBER_HOUR.search(member.name)
            handle = tar.extractfile(member) if member.isfile() else None
            if match is None or handle is None:
                continue
            hour = datetime.strptime(match.group(1), "%Y%m%d%H").replace(tzinfo=UTC)
            if last_hour is not None and hour > last_hour:
                return
            carry = ""
            while chunk := handle.read(_READ_CHUNK):
                parts = (carry + chunk.decode("latin-1")).split(_SOH)
                carry = parts.pop()
                for part in parts:
                    yield hour, part.split(_ETX, 1)[0]
            if carry:
                yield hour, carry.split(_ETX, 1)[0]


def select_bulletins(products: Iterable[tuple[datetime, str]]) -> Iterator[Bulletin]:
    for order, (hour, product) in enumerate(products):
        text = product.replace("\r", "")
        heading = _WMO_HEADING.search(text, 0, _HEADING_WINDOW)
        if heading is None:
            continue
        line = " ".join(heading.group(0).split())
        body = text[heading.start() :].strip()
        if keep_bulletin(line, body):
            yield Bulletin(heading=line, text=body + "\n", hour=hour, order=order)


class _ChunkReader(io.RawIOBase):
    """A readable file over an iterator of byte chunks (an HTTP response body)."""

    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks
        self._pending = b""
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        while not self._pending:
            try:
                self._pending = next(self._chunks)
            except StopIteration:
                return 0
            self.bytes_read += len(self._pending)
        size = min(len(buffer), len(self._pending))
        buffer[:size] = self._pending[:size]
        self._pending = self._pending[size:]
        return size


def stream_noaaport_day(day: date, out_dir: Path, *, last_hour: int = 23) -> Path:
    """Stream one IEM day file and keep its bulletins as ``<out_dir>/<YYYYMMDD>.jsonl``."""
    url = NOAAPORT_DAY_URL.format(day=day)
    until = datetime(day.year, day.month, day.day, last_hour, tzinfo=UTC)
    target = out_dir / f"{day:%Y%m%d}.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    timeout = httpx.Timeout(120.0, connect=20.0)
    with (
        httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=timeout) as client,
        client.stream("GET", url) as response,
    ):
        response.raise_for_status()
        reader = _ChunkReader(response.iter_raw())
        stream = io.BufferedReader(reader, buffer_size=1 << 20)
        with target.open("w", encoding="utf-8") as handle:
            for bulletin in select_bulletins(iter_products(stream, last_hour=until)):
                handle.write(json.dumps(_bulletin_row(bulletin)) + "\n")
                kept += 1
    summary = {
        "url": url,
        "fetched_at": timeutil.to_iso(datetime.now(UTC)),
        "last_hour": timeutil.to_iso(until),
        "bytes_read": reader.bytes_read,
        "bulletins": kept,
    }
    target.with_suffix(".source.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"  {day:%Y-%m-%d}: {reader.bytes_read / 1e6:.0f} MB streamed, {kept} bulletins kept")
    return target


def _bulletin_row(bulletin: Bulletin) -> dict[str, object]:
    return {
        "heading": bulletin.heading,
        "hour": timeutil.to_iso(bulletin.hour),
        "order": bulletin.order,
        "text": bulletin.text,
    }


def read_noaaport_dir(directory: Path) -> list[Bulletin]:
    """Every bulletin ``noaaport`` saved under ``directory``, in arrival order.

    A slot's state before a window is its last bulletin in these days, so they must be
    consecutive, every day must have finished streaming, and only the last may stop early.
    """
    paths = sorted(directory.glob("*.jsonl"))
    _check_days(paths)
    bulletins: list[Bulletin] = []
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                bulletins.append(
                    Bulletin(
                        heading=row["heading"],
                        text=row["text"],
                        hour=timeutil.parse_iso(row["hour"]),
                        order=int(row["order"]),
                    )
                )
    return sorted(bulletins, key=lambda bulletin: (bulletin.hour, bulletin.order))


def _check_days(paths: Sequence[Path]) -> None:
    if not paths:
        raise SystemExit("no NOAAPort days saved there; run the noaaport command first")
    days: list[tuple[date, int]] = []
    for path in paths:
        summary = path.with_suffix(".source.json")
        if not summary.is_file():
            raise SystemExit(f"{path.name} did not finish streaming; stream that day again")
        last_hour = timeutil.parse_iso(json.loads(summary.read_text())["last_hour"]).hour
        days.append((date.fromisoformat(path.stem), last_hour))
    for (day, last_hour), (after, _) in pairwise(days):
        if after - day != timedelta(days=1):
            raise SystemExit(f"NOAAPort days are not consecutive after {day}; stream the gap")
        if last_hour != 23:
            raise SystemExit(f"{day} stops at {last_hour:02d}Z; only the last day may stop early")
    print(f"  NOAAPort days {days[0][0]} to {days[-1][0]} (the last to {days[-1][1]:02d}Z)")


def archive_gaps(
    bulletins: Iterable[Bulletin], start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    """Spans in ``[start, end]`` longer than an hour with no bulletin at all.

    The METAR collectives alone arrive every 30 minutes, so a longer silence is the
    archive's: products issued then are missing from it, and from a case built on it.
    """
    times = sorted({bulletin.received_at for bulletin in bulletins})
    return [
        (before, after)
        for before, after in pairwise(times)
        if after - before > _ARCHIVE_SILENCE and before < end and after > start
    ]


def merge_copies[T](
    items: Iterable[T], *, key: Callable[[T], Hashable], bulletin: Callable[[T], Bulletin]
) -> list[tuple[datetime, T]]:
    """One ``(first arrival, best copy)`` per key, in the order the first copies arrived.

    NOAAPort relays many bulletins twice, wrapped differently and sometimes with characters
    the relay could not carry turned into ``?``. The copy kept has the fewest ``?``, then the
    most text (one copy may lack a remark), then arrived first; it counts as available from
    the first copy's arrival.
    """
    groups: dict[Hashable, list[T]] = {}
    for item in sorted(items, key=lambda item: (bulletin(item).hour, bulletin(item).order)):
        groups.setdefault(key(item), []).append(item)
    merged: list[tuple[datetime, T]] = []
    for copies in groups.values():
        best = min(
            copies,
            key=lambda copy: (bulletin(copy).text.count("?"), -len(bulletin(copy).body())),
        )
        merged.append((min(bulletin(copy).received_at for copy in copies), best))
    return sorted(merged, key=lambda pair: pair[0])


# --- VA SIGMETs: AWC snapshots, the census, or NOAAPort bulletins in AWC's JSON ------------


def fetch_awc_sigmets(
    fetcher: ArchiveFetcher, start: datetime, end: datetime, step: timedelta, case_dir: Path
) -> list[ReplayRecord]:
    """One AWC ``date=`` snapshot per step, stored under the live poller's URL."""
    live_url = build_url(SIGMET_URL, SIGMET_PARAMS)
    oldest = datetime.now(UTC) - timedelta(days=AWC_HISTORY_DAYS)
    if start < oldest:
        print(f"warning: AWC keeps 30 days; snapshots before {oldest:%Y-%m-%d %H:%MZ} will fail")
    records: list[ReplayRecord] = []
    at = start
    while at <= end:
        try:
            status, content = fetcher.get(awc_history_url(live_url, at))
        except RuntimeError as exc:  # one missing hour should not end the backfill
            print(f"  {at:%Y-%m-%d %H:%MZ}: {exc}")
        else:
            records.append(
                _store(case_dir, FeedId.SIGMET, live_url, at, content, status, JSON_TYPE)
            )
        at += step
    print(f"  fetched {len(records)} AWC SIGMET snapshots")
    return records


def awc_history_url(live_url: str, at: datetime) -> str:
    """The AWC request for what ``live_url`` answered at ``at`` (30 days of history)."""
    return build_url(live_url, {"date": at.strftime("%Y%m%d_%H%M")})


def import_census_sigmets(
    saved: list[Saved], start: datetime, end: datetime, case_dir: Path
) -> list[ReplayRecord]:
    """The census's hourly AWC ``date=`` snapshots, stored under the live poller's URL."""
    live_url = build_url(SIGMET_URL, SIGMET_PARAMS)
    records: list[ReplayRecord] = []
    for item in saved:
        match = _SNAPSHOT_DATE.search(item.url)
        if match is None or not item.url.startswith(SIGMET_URL) or item.status != 200:
            continue
        at = datetime.strptime("".join(match.groups()), "%Y%m%d%H%M").replace(tzinfo=UTC)
        if start <= at <= end:
            content = item.content()
            records.append(
                _store(case_dir, FeedId.SIGMET, live_url, at, content, 200, "application/json")
            )
    print(f"  imported {len(records)} SIGMET snapshots")
    return records


_SIGMET_START = re.compile(
    r"\b(?P<fir>[A-Z]{4}) SIGMET (?P<series>[A-Z0-9]{1,4}) VALID (?P<start>\d{6})/(?P<end>\d{6})"
    r"(?: (?P<mwo>[A-Z]{4})-)?"
)
_FIR_NAME = re.compile(r"\s*(?P<fir>[A-Z]{4}) (?P<name>[A-Z][A-Z ]*?) (?:FIR|UIR|CTA)\b")
_CNL_SIGMET = re.compile(r"\bCNL SIGMET (?P<series>[A-Z0-9]{1,4}) (?P<start>\d{6})/\d{6}\b")
_FCST_POLYGON = re.compile(r"\bFCST\b.*?\bWI\b")


@dataclass(frozen=True)
class SigmetText:
    """What a raw VA SIGMET bulletin says about itself, for wrapping it in AWC's JSON."""

    bulletin: Bulletin
    fir: str
    series: str
    valid_from: datetime
    valid_to: datetime
    mwo: str | None
    fir_name: str | None
    cancels: str | None
    """Series id of the SIGMET a ``CNL SIGMET`` bulletin cancels."""

    @property
    def copy_key(self) -> tuple[str, str, datetime, datetime, str | None, str]:
        """Copies of one bulletin share it; a reissue with another VALID group or a
        correction (``CCA``) does not."""
        correction = self.bulletin.heading.split()[3:]
        return (
            self.fir,
            self.series,
            self.valid_from,
            self.valid_to,
            self.cancels,
            correction[0] if correction else "",
        )


def read_sigmet(bulletin: Bulletin) -> SigmetText | None:
    """The FIR, series, validity and any cancellation of a VA SIGMET bulletin."""
    body = bulletin.body()
    match = _SIGMET_START.search(body)
    if match is None:
        return None
    valid_from = timeutil.parse_ddhhmm(match.group("start"), bulletin.issued_at)
    valid_to = timeutil.parse_ddhhmm(match.group("end"), valid_from)
    name = _FIR_NAME.match(body, match.end())
    cancel = _CNL_SIGMET.search(body, match.end())
    fir = match.group("fir")
    return SigmetText(
        bulletin=bulletin,
        fir=fir,
        series=match.group("series"),
        valid_from=valid_from,
        valid_to=valid_to,
        mwo=match.group("mwo"),
        fir_name=f"{fir} {name.group('name')}" if name and name.group("fir") == fir else None,
        cancels=cancel.group("series") if cancel else None,
    )


def isigmet_records(sigmet: SigmetText, arrived: datetime, valid_to: datetime) -> list[dict]:
    """The bulletin in the isigmet JSON fields the parser reads, with nothing decoded.

    Geometry, levels, movement and intensity stay in ``rawSigmet`` for the parser to read,
    as it does whenever AWC leaves them out. A SIGMET with a forecast polygon gets a second
    record whose series ends in ``F``, as AWC splits them (SEFG 2/2F in the census).
    """
    record: dict[str, Any] = {
        "icaoId": sigmet.mwo or sigmet.bulletin.cccc,
        "firId": sigmet.fir,
        "receiptTime": timeutil.to_iso(arrived),
        "validTimeFrom": int(sigmet.valid_from.timestamp()),
        "validTimeTo": int(valid_to.timestamp()),
        "seriesId": sigmet.series,
        "hazard": "VA",
        "rawSigmet": sigmet.bulletin.text.rstrip("\n"),
    }
    if sigmet.fir_name:
        record["firName"] = sigmet.fir_name
    records = [record]
    if sigmet.cancels is None and _FCST_POLYGON.search(sigmet.bulletin.body()):
        records.append({**record, "seriesId": f"{sigmet.series}F"})
    return records


def isigmet_snapshots(
    sigmets: Sequence[tuple[datetime, SigmetText]], start: datetime, end: datetime
) -> list[tuple[datetime, list[dict]]]:
    """The isigmet list as it stood at ``start`` and after each later arrival up to ``end``.

    A list holds every SIGMET that has arrived and not yet ended. A later bulletin with the
    same FIR and series (a reissue or correction) replaces the earlier one. ``CNL SIGMET``
    bulletins are listed as records of their own, and end the SIGMET they cancel at their
    start: AWC shows a cancellation that way, as a shorter ``validTimeTo`` (research/14).
    """
    arrivals = sorted(sigmets, key=lambda pair: pair[0])  # stable: ties keep arrival order
    times = [start, *sorted({at for at, _ in arrivals if start < at <= end})]
    snapshots: list[tuple[datetime, list[dict]]] = []
    for at in times:
        current: dict[tuple[str, str], tuple[datetime, SigmetText]] = {}
        ended: dict[tuple[str, str], datetime] = {}
        for arrived, sigmet in arrivals:
            if arrived > at:
                break
            current[(sigmet.fir, sigmet.series)] = (arrived, sigmet)
            ended.pop((sigmet.fir, sigmet.series), None)
            if sigmet.cancels is not None and (sigmet.fir, sigmet.cancels) in current:
                ended[(sigmet.fir, sigmet.cancels)] = sigmet.valid_from
        records: list[dict] = []
        for key, (arrived, sigmet) in current.items():
            valid_to = min(sigmet.valid_to, ended.get(key, sigmet.valid_to))
            if valid_to > at:
                records += isigmet_records(sigmet, arrived, valid_to)
        records.sort(key=lambda item: (item["receiptTime"], item["firId"], item["seriesId"]))
        snapshots.append((at, records))
    return snapshots


def noaaport_sigmets(
    bulletins: Iterable[Bulletin], firs: Sequence[str]
) -> list[tuple[datetime, SigmetText]]:
    sigmets = [
        sigmet
        for bulletin in bulletins
        if bulletin.heading[:2] in ("WV", "WS")
        and (sigmet := read_sigmet(bulletin)) is not None
        and sigmet.fir in firs
    ]
    return merge_copies(
        sigmets, key=lambda item: item.copy_key, bulletin=lambda item: item.bulletin
    )


def import_noaaport_sigmets(
    bulletins: Iterable[Bulletin],
    firs: Sequence[str],
    start: datetime,
    end: datetime,
    case_dir: Path,
) -> list[ReplayRecord]:
    live_url = build_url(SIGMET_URL, SIGMET_PARAMS)
    sigmets = noaaport_sigmets(bulletins, firs)
    records = [
        _store(case_dir, FeedId.SIGMET, live_url, at, _json_bytes(snapshot), 200, JSON_TYPE)
        for at, snapshot in isigmet_snapshots(sigmets, start, end)
    ]
    in_window = sum(1 for at, _ in sigmets if start < at <= end)
    cancels = sum(1 for at, sigmet in sigmets if start < at <= end and sigmet.cancels)
    print(
        f"  {in_window} {'/'.join(firs)} SIGMET bulletins in the window ({cancels} CNL), "
        f"{len(records)} isigmet snapshots"
    )
    return records


# --- Darwin VAAs: NOAAPort FVAU bulletins under their tgftp slots --------------------------

_DARWIN_HEADING = re.compile(r"^FVAU(0[1-9]|10) ADRM\b")
_VAA_NUMBER = re.compile(r"^ADVISORY NR:\s*(\S+)", re.MULTILINE)
_VAA_DTG = re.compile(r"^DTG:\s*(\d{8}/\d{4})Z", re.MULTILINE)
_VAA_VOLCANO = re.compile(r"^VOLCANO:\s*(.+?)\s*$", re.MULTILINE)
_NO_VOLCANO: Final = frozenset({"NOTICE 999999", "UNKNOWN"})
_NO_VOLCANO_SERIES: Final = "NOTICE/UNKNOWN"


@dataclass(frozen=True)
class DarwinVaa:
    bulletin: Bulletin
    slot: int
    advisory_nr: str
    volcano: str
    dtg: datetime

    @property
    def copy_key(self) -> tuple[str, str, datetime]:
        return self.bulletin.heading, self.advisory_nr, self.dtg


def read_darwin_vaa(bulletin: Bulletin) -> DarwinVaa | None:
    heading = _DARWIN_HEADING.match(bulletin.heading)
    number = _VAA_NUMBER.search(bulletin.text)
    dtg = _VAA_DTG.search(bulletin.text)
    volcano = _VAA_VOLCANO.search(bulletin.text)
    if heading is None or number is None or dtg is None or volcano is None:
        return None
    return DarwinVaa(
        bulletin=bulletin,
        slot=int(heading.group(1)),
        advisory_nr=number.group(1),
        volcano=" ".join(volcano.group(1).split()),
        dtg=timeutil.parse_slash_dtg(dtg.group(1)),
    )


def darwin_vaas(bulletins: Iterable[Bulletin]) -> list[tuple[datetime, DarwinVaa]]:
    """Darwin VAAs, one per advisory, each at max(first arrival, DTG)."""
    vaas = [vaa for bulletin in bulletins if (vaa := read_darwin_vaa(bulletin)) is not None]
    merged = merge_copies(vaas, key=lambda vaa: vaa.copy_key, bulletin=lambda vaa: vaa.bulletin)
    return sorted(
        ((max(arrived, vaa.dtg), vaa) for arrived, vaa in merged), key=lambda pair: pair[0]
    )


def retransmissions(
    vaas: Sequence[tuple[datetime, DarwinVaa]],
) -> list[tuple[datetime, DarwinVaa]]:
    """Bulletins with an older DTG than one their slot had already received.

    NOAAPort sometimes replays a backlog: on 23 Sep 2026 10-15Z it re-sent Darwin's
    bulletins of 14-15 Sep. A slot holds Darwin's newest advisory on that heading, so a
    replayed one is not a slot state; taken as one, it would push the current advisory out.
    """
    newest: dict[int, datetime] = {}
    stale: list[tuple[datetime, DarwinVaa]] = []
    for at, vaa in vaas:
        if vaa.dtg < newest.get(vaa.slot, vaa.dtg):
            stale.append((at, vaa))
        else:
            newest[vaa.slot] = vaa.dtg
    return stale


def darwin_slot_states(
    vaas: Sequence[tuple[datetime, DarwinVaa]], start: datetime, end: datetime
) -> list[tuple[datetime, DarwinVaa]]:
    """What each tgftp slot held: every bulletin in the window, and each slot's last before.

    A slot keeps its bulletin until the next one replaces it, so the last one before
    ``start`` is what the slot served when the replay begins; without it the replay would
    serve that slot's first bulletin of the window before it was issued. Retransmissions
    are left out.
    """
    stale = set(retransmissions(vaas))
    before: dict[int, tuple[datetime, DarwinVaa]] = {}
    within: list[tuple[datetime, DarwinVaa]] = []
    for at, vaa in vaas:
        if at > end or (at, vaa) in stale:
            continue
        if at >= start:
            within.append((at, vaa))
        elif vaa.slot not in before or at >= before[vaa.slot][0]:
            before[vaa.slot] = (at, vaa)
    return sorted([*before.values(), *within], key=lambda pair: (pair[0], pair[1].slot))


def advisory_runs(
    vaas: Iterable[DarwinVaa], elsewhere: Iterable[DarwinVaa] = ()
) -> dict[str, tuple[int, int, list[int]]]:
    """Per volcano: first and last advisory number seen, and the numbers missing between.

    A number found in ``elsewhere`` (the other streamed bulletins) is not missing: Darwin
    sometimes issues one just before a window out of numeric order. Darwin numbers its
    notices (``NOTICE 999999``) and its advisories for an unknown source (``UNKNOWN``) in
    one series, so they count as one run.
    """
    numbers, known = _advisory_numbers(vaas), _advisory_numbers(elsewhere)
    runs: dict[str, tuple[int, int, list[int]]] = {}
    for volcano, seen in sorted(numbers.items()):
        low, high = min(seen), max(seen)
        found = seen | known.get(volcano, set())
        runs[volcano] = (low, high, [n for n in range(low, high + 1) if n not in found])
    return runs


def _advisory_numbers(vaas: Iterable[DarwinVaa]) -> dict[str, set[int]]:
    numbers: dict[str, set[int]] = {}
    for vaa in vaas:
        _, _, serial = vaa.advisory_nr.partition("/")
        series = _NO_VOLCANO_SERIES if vaa.volcano in _NO_VOLCANO else vaa.volcano
        if serial.isdigit():
            numbers.setdefault(series, set()).add(int(serial))
    return numbers


def unheld_slots(states: Sequence[tuple[datetime, DarwinVaa]], start: datetime) -> list[int]:
    """Slots with a bulletin in the window but none at or before its start."""
    held = {vaa.slot for at, vaa in states if at <= start}
    return sorted({vaa.slot for at, vaa in states if at > start} - held)


def import_darwin(
    bulletins: Iterable[Bulletin], start: datetime, end: datetime, case_dir: Path
) -> list[ReplayRecord]:
    """Each slot's bulletins, and an empty 204 record at ``start`` for a slot whose earlier
    bulletin is not in the streamed days: the poller reads that as an unreadable slot, so the
    slot's first bulletin of the window cannot show before its time."""
    vaas = darwin_vaas(bulletins)
    states = darwin_slot_states(vaas, start, end)
    replayed = [vaa for at, vaa in retransmissions(vaas) if at <= end]
    if replayed:
        print(f"  skipped {len(replayed)} Darwin bulletins re-sent after newer ones on their slots")
    records = [
        _store(
            case_dir,
            FeedId.VAAC_DARWIN,
            _slot_url(vaa.slot),
            at,
            vaa.bulletin.text.encode("latin-1"),
            200,
            "text/plain",
        )
        for at, vaa in states
    ]
    unheld = unheld_slots(states, start)
    markers = [
        _store(case_dir, FeedId.VAAC_DARWIN, _slot_url(slot), start, b"", 204, None)
        for slot in unheld
    ]
    records = markers + records
    held = sorted({vaa.slot for at, vaa in states if at <= start})
    within = [vaa for at, vaa in states if at > start]
    print(
        f"  {len(within)} Darwin bulletins in the window; slots held at its start: "
        f"{', '.join(f'FVAU{slot:02d}' for slot in held) or 'none'}"
    )
    if unheld:
        names = ", ".join(f"FVAU{slot:02d}" for slot in unheld)
        print(f"  no bulletin before the window for {names}: an empty record holds each")
    issued = [vaa for vaa in within if start <= vaa.dtg <= end]  # not re-sent old ones
    for volcano, (low, high, missing) in advisory_runs(issued, (v for _, v in vaas)).items():
        gap = f"missing {', '.join(map(str, missing))}" if missing else "no gaps"
        print(f"    {volcano}: {low}-{high}, {gap}")
    return records


def _slot_url(slot: int) -> str:
    if slot > len(DARWIN_BULLETIN_URLS):
        raise SystemExit(
            f"FVAU{slot:02d} is not among the slots tephra.feeds.vaac polls "
            f"({len(DARWIN_BULLETIN_URLS)}); a replay could never serve it"
        )
    return DARWIN_BULLETIN_URLS[slot - 1]


# --- VONA list pages -------------------------------------------------------------------------


def import_census_vona_pages(saved: list[Saved], case_dir: Path) -> list[ReplayRecord]:
    """The census's MAGMA VONA list pages, under the URL the poller uses for each page."""
    records: list[ReplayRecord] = []
    for item in saved:
        match = _VONA_PAGE.match(item.url)
        if match is None or item.status != 200:
            continue
        page = int(match.group(1) or 1)
        url = build_url(VONA_LIST_URL, None if page == 1 else {"page": str(page)})
        records.append(
            _store(case_dir, FeedId.VONA, url, item.fetched_at, item.content(), 200, "text/html")
        )
    print(f"  imported {len(records)} VONA list pages")
    return records


def read_census(census_dir: Path) -> list[Saved]:
    with (census_dir / "manifest.tsv").open(encoding="utf-8", newline="") as handle:
        return [
            Saved(
                fetched_at=_utc(row["fetched_utc"]),
                status=int(row["http_status"]),
                url=row["url"],
                path=census_dir / row["local_path"],
                sha256=row["sha256"],
            )
            for row in csv.DictReader(handle, delimiter="\t")
        ]


# --- METARs from the IEM ASOS archive, in AWC's JSON shape ------------------------------------

IEM_ASOS_URL: Final = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
METAR_STEP: Final = timedelta(minutes=30)
_METRES_PER_SM: Final = 1609.344
_METAR_SKIP = frozenset({"METAR", "SPECI", "COR", "AUTO", "NIL"})
_METAR_END = frozenset({"NOSIG", "TEMPO", "BECMG", "RMK"})
_METAR_WIND = re.compile(r"^(?:\d{3}|VRB)\d{2,3}(?:G\d{2,3})?(?:KT|MPS)$|^\d{3}V\d{3}$")
_METAR_VISIBILITY = re.compile(r"^(\d{4})(?:NDV|[NSEW]{1,2})?$")
_METAR_RVR = re.compile(r"^R\d{2}[LCR]?/")
_METAR_CLOUD = re.compile(r"^(FEW|SCT|BKN|OVC)(\d{3})(?:CB|TCU|///)?$")
_METAR_VV = re.compile(r"^VV(\d{3})$")
_METAR_TEMPERATURE = re.compile(r"^M?\d{2}/(?:M?\d{2})?$")
_METAR_WEATHER = re.compile(
    r"^(?:[+-]|VC)?(?:MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)*$"
)


@dataclass(frozen=True)
class IemMetar:
    station: str
    observed_at: datetime
    raw: str


def iem_asos_url(stations: Iterable[str], start: datetime, end: datetime) -> str:
    """One IEM request for every station's raw METARs and SPECIs (IEM asks for one call per
    case, not one per station)."""
    pairs = [("station", station) for station in sorted(set(stations))]
    for suffix, at in (("1", start), ("2", end)):
        pairs += [
            (f"year{suffix}", str(at.year)),
            (f"month{suffix}", str(at.month)),
            (f"day{suffix}", str(at.day)),
            (f"hour{suffix}", str(at.hour)),
        ]
    pairs += [
        ("data", "metar"),
        ("tz", "Etc/UTC"),
        ("format", "onlycomma"),
        ("latlon", "no"),
        ("missing", "M"),
        ("trace", "T"),
        ("direct", "no"),
        ("report_type", "3"),
        ("report_type", "4"),
    ]
    return f"{IEM_ASOS_URL}?{urlencode(pairs)}"


def parse_iem_csv(text: str) -> list[IemMetar]:
    metars: list[IemMetar] = []
    for row in csv.DictReader(io.StringIO(text)):
        raw = " ".join((row.get("metar") or "").split())
        if not raw or raw == "M":
            continue
        observed = datetime.strptime(row["valid"], "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
        metars.append(IemMetar(station=row["station"].upper(), observed_at=observed, raw=raw))
    return sorted(metars, key=lambda metar: (metar.station, metar.observed_at))


def awc_metar(metar: IemMetar) -> dict[str, Any]:
    """An IEM METAR in the AWC JSON fields the parser reads, decoded from its text.

    ``visib`` is in statute miles as AWC renders it (``"6+"`` for 9999 or CAVOK), clouds
    are ``{cover, base}`` in feet, and ``fltCat`` follows AWC's VFR/MVFR/IFR/LIFR limits.
    """
    visibility_m: int | None = None
    weather: list[str] = []
    clouds: list[dict[str, Any]] = []
    vertical: int | None = None
    for token in metar.raw.split()[2:]:
        if token in _METAR_END or _METAR_TEMPERATURE.match(token):
            break
        if token in _METAR_SKIP or _METAR_WIND.match(token) or _METAR_RVR.match(token):
            continue
        if token == "CAVOK":
            visibility_m = 9999
        elif (match := _METAR_VISIBILITY.match(token)) and visibility_m is None:
            visibility_m = int(match.group(1))
        elif match := _METAR_CLOUD.match(token):
            clouds.append({"cover": match.group(1), "base": int(match.group(2)) * 100})
        elif match := _METAR_VV.match(token):
            vertical = int(match.group(1)) * 100
        elif len(token) >= 2 and _METAR_WEATHER.match(token):
            weather.append(token)
    record: dict[str, Any] = {
        "icaoId": metar.station,
        "obsTime": int(metar.observed_at.timestamp()),
        "reportTime": timeutil.to_iso(metar.observed_at),
        "rawOb": metar.raw,
        "visib": _awc_visibility(visibility_m),
        "wxString": " ".join(weather) or None,
        "clouds": clouds,
        "fltCat": _flight_category(visibility_m, clouds, vertical),
    }
    if vertical is not None:
        record["vertVis"] = vertical
    return record


def _awc_visibility(metres: int | None) -> str | float | None:
    if metres is None:
        return None
    return "6+" if metres >= 9999 else round(metres / _METRES_PER_SM, 2)


def _flight_category(
    visibility_m: int | None, clouds: Sequence[dict[str, Any]], vertical: int | None
) -> str | None:
    if visibility_m is None:
        return None
    bases = [layer["base"] for layer in clouds if layer["cover"] in ("BKN", "OVC")]
    ceiling = min([*bases, *([vertical] if vertical is not None else [])], default=None)
    miles = visibility_m / _METRES_PER_SM
    if miles < 1 or (ceiling is not None and ceiling < 500):
        return "LIFR"
    if miles < 3 or (ceiling is not None and ceiling < 1000):
        return "IFR"
    if miles <= 5 or (ceiling is not None and ceiling <= 3000):
        return "MVFR"
    return "VFR"


def metar_response(metars: Sequence[IemMetar], stations: Iterable[str], at: datetime) -> bytes:
    """AWC's answer at ``at`` for ``stations``: the latest METAR of each at or before ``at``."""
    wanted = {station.upper() for station in stations}
    latest: dict[str, IemMetar] = {}
    for metar in metars:
        if metar.station in wanted and metar.observed_at <= at:
            latest[metar.station] = metar  # metars are in time order per station
    return _json_bytes([awc_metar(latest[station]) for station in sorted(latest)])


# --- winds from the Open-Meteo Historical Forecast API --------------------------------------

OPEN_METEO_HISTORICAL_URL: Final = "https://historical-forecast-api.open-meteo.com/v1/forecast"


def historical_wind_url(live_url: str, at: datetime) -> str:
    """The Historical Forecast request for what the live winds URL answers at ``at``.

    The live call asks for ``past_hours`` before the current hour and ``forecast_hours``
    from it; the archive takes the same span as ``start_hour``/``end_hour``. Every other
    parameter is kept, so the answer has the live shape and ``parse_winds`` reads it as is.
    """
    query = dict(parse_qsl(urlsplit(live_url).query))
    past = int(query.pop("past_hours", "0"))
    ahead = int(query.pop("forecast_hours", "24"))
    hour = at.replace(minute=0, second=0, microsecond=0)
    query["start_hour"] = (hour - timedelta(hours=past)).strftime("%Y-%m-%dT%H:%M")
    query["end_hour"] = (hour + timedelta(hours=ahead - 1)).strftime("%Y-%m-%dT%H:%M")
    return build_url(OPEN_METEO_HISTORICAL_URL, query)


# --- ADS-B from adsb.lol globe_history heatmaps ----------------------------------------------

ADSB_HEATMAP_URL: Final = "https://adsb.lol/globe_history/{at:%Y/%m/%d}/heatmap/{index:02d}.bin.ttf"
ADSB_STEP: Final = timedelta(seconds=60)
ADSB_DECODE_BOX: Final = (-20.0, 85.0, 15.0, 150.0)
"""South, west, north, east: Indonesia and 250 nm around it, where the query points lie."""
_HEATMAP_SLICE: Final = 0x0E7F7C9D
_HEATMAP_INFO: Final = 1 << 30
_HEATMAP_NON_ICAO: Final = 1 << 24
_HEATMAP_GROUND: Final = -123
_HEATMAP_NO_ALTITUDE: Final = -124
_HEATMAP_ROW = np.dtype(
    [("hex", "<i4"), ("lat", "<i4"), ("lon", "<i4"), ("alt", "<i2"), ("gs", "<i2")]
)
_POSITION_MAX_AGE_MS: Final = 60_000
"""readsb drops a position from its API after 60 s; so does a reconstructed answer."""
_TRACK_MIN_GAP_MS: Final = 20_000
_TRACK_MAX_GAP_MS: Final = 180_000
_TRACK_MIN_NM: Final = 0.2
_POINT_URL = re.compile(r"/v2/point/(-?\d+(?:\.\d+)?)/(-?\d+(?:\.\d+)?)/(\d+)$")


@dataclass(frozen=True)
class Heatmap:
    """Airborne-or-ground ICAO positions inside the decode box, in time order, and the
    callsign reports of those aircraft."""

    time_ms: np.ndarray
    addr: np.ndarray
    lat_e6: np.ndarray
    lon_e6: np.ndarray
    alt: np.ndarray
    gs: np.ndarray
    callsigns: dict[int, list[tuple[int, str]]] = field(default_factory=dict)

    def callsign_at(self, addr: int, at_ms: int) -> str | None:
        reports = [text for when, text in self.callsigns.get(addr, []) if when <= at_ms]
        return reports[-1] if reports else None


def decode_heatmap(raw: bytes, box: tuple[float, float, float, float] = ADSB_DECODE_BOX) -> Heatmap:
    """A readsb heatmap file (globe_history/.../heatmap/NN.bin.ttf, gzip).

    16-byte little-endian rows: int32 hex, int32 lat x1e6, int32 lon x1e6, int16 altitude in
    25 ft steps (-123 ground, -124 unknown), int16 ground speed x10. The file starts with an
    index of one row per slice; a slice marker row (hex 0x0e7f7c9d) carries the slice time
    in ms as lat<<32 | lon, and the rows after it belong to that slice. A row whose lat is at
    least 2**30 is an info row with the callsign in bytes 8-15. Addresses with bit 24 set are
    not ICAO addresses and are skipped (readsb globe_index.c).
    """
    data = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
    count = len(data) // _HEATMAP_ROW.itemsize
    rows = np.frombuffer(data, dtype=_HEATMAP_ROW, count=count)
    slices = int(rows["hex"][0])
    rows = rows[slices:]
    raw_rows = np.frombuffer(data, dtype=np.uint8, count=count * 16).reshape(count, 16)[slices:]
    marker = rows["hex"] == _HEATMAP_SLICE
    stamps = (rows["lat"][marker].astype(np.int64) & 0xFFFFFFFF) << 32 | (
        rows["lon"][marker].astype(np.int64) & 0xFFFFFFFF
    )
    owner = np.cumsum(marker) - 1
    keep = ~marker & (owner >= 0) & ((rows["hex"] & _HEATMAP_NON_ICAO) == 0)
    info = keep & (rows["lat"] >= _HEATMAP_INFO)
    south, west, north, east = box
    position = (
        keep
        & ~info
        & (rows["lat"] >= south * 1e6)
        & (rows["lat"] <= north * 1e6)
        & (rows["lon"] >= west * 1e6)
        & (rows["lon"] <= east * 1e6)
    )
    addr = rows["hex"] & 0xFFFFFF
    seen = set(np.unique(addr[position]).tolist())
    callsigns: dict[int, list[tuple[int, str]]] = {}
    for index in np.flatnonzero(info & np.isin(addr, list(seen))):
        text = bytes(raw_rows[index, 8:16]).split(b"\0", 1)[0].decode("ascii", "replace").strip()
        if text:
            callsigns.setdefault(int(addr[index]), []).append((int(stamps[owner[index]]), text))
    return Heatmap(
        time_ms=stamps[owner[position]],
        addr=addr[position].astype(np.int32),
        lat_e6=rows["lat"][position].astype(np.int32),
        lon_e6=rows["lon"][position].astype(np.int32),
        alt=rows["alt"][position].astype(np.int16),
        gs=rows["gs"][position].astype(np.int16),
        callsigns=callsigns,
    )


def join_heatmaps(parts: Sequence[Heatmap]) -> Heatmap:
    callsigns: dict[int, list[tuple[int, str]]] = {}
    for part in parts:
        for addr, reports in part.callsigns.items():
            callsigns.setdefault(addr, []).extend(reports)
    for reports in callsigns.values():
        reports.sort()
    joined = {
        name: np.concatenate([getattr(part, name) for part in parts])
        for name in ("time_ms", "addr", "lat_e6", "lon_e6", "alt", "gs")
    }
    order = np.argsort(joined["time_ms"], kind="stable")
    return Heatmap(**{name: values[order] for name, values in joined.items()}, callsigns=callsigns)


def point_response(
    heatmap: Heatmap, lat: float, lon: float, radius_nm: float, at: datetime
) -> dict[str, Any]:
    """An adsb.lol ``/v2/point`` answer at ``at``, rebuilt from heatmap positions.

    Each aircraft whose latest position in the last 60 s lies within ``radius_nm`` is listed
    with the heatmap's hex, callsign, position, altitude and ground speed. ``track`` is the
    bearing from an earlier position 20-180 s before; ``seen_pos`` and ``seen`` are the
    position's age. Type, registration and selected altitude are not in a heatmap.
    """
    at_ms = round(at.timestamp() * 1000)
    low = int(np.searchsorted(heatmap.time_ms, at_ms - _TRACK_MAX_GAP_MS, side="right"))
    high = int(np.searchsorted(heatmap.time_ms, at_ms, side="right"))
    window = np.arange(low, high)
    by_aircraft = window[np.lexsort((heatmap.time_ms[window], heatmap.addr[window]))]
    addrs = heatmap.addr[by_aircraft]
    if not len(addrs):
        return {"ac": [], "now": at_ms, "total": 0}
    starts = np.flatnonzero(np.r_[True, addrs[1:] != addrs[:-1]])
    ends = np.r_[starts[1:], len(addrs)]
    entries: list[dict[str, Any]] = []
    for first, stop in zip(starts.tolist(), ends.tolist(), strict=True):
        index = int(by_aircraft[stop - 1])
        seen_ms = at_ms - int(heatmap.time_ms[index])
        here = (heatmap.lat_e6[index] / 1e6, heatmap.lon_e6[index] / 1e6)
        if seen_ms > _POSITION_MAX_AGE_MS or distance_nm(lat, lon, *here) > radius_nm:
            continue
        history = by_aircraft[first:stop]
        entries.append(_aircraft_entry(heatmap, index, history, at_ms, seen_ms))
    entries.sort(key=lambda entry: entry["hex"])
    return {"ac": entries, "now": at_ms, "total": len(entries)}


def _aircraft_entry(
    heatmap: Heatmap, index: int, history: np.ndarray, at_ms: int, seen_ms: int
) -> dict[str, Any]:
    addr = int(heatmap.addr[index])
    lat, lon = heatmap.lat_e6[index] / 1e6, heatmap.lon_e6[index] / 1e6
    entry: dict[str, Any] = {"hex": f"{addr:06x}"}
    callsign = heatmap.callsign_at(addr, at_ms)
    if callsign:
        entry["flight"] = callsign
    altitude = int(heatmap.alt[index])
    if altitude == _HEATMAP_GROUND:
        entry["alt_baro"] = "ground"
    elif altitude != _HEATMAP_NO_ALTITUDE:
        entry["alt_baro"] = altitude * 25
    speed = int(heatmap.gs[index])
    if speed >= 0:
        entry["gs"] = speed / 10
    track = _derived_track(heatmap, index, history)
    if track is not None:
        entry["track"] = track
    seen_s = round(seen_ms / 1000, 1)
    entry.update(lat=round(float(lat), 6), lon=round(float(lon), 6), seen_pos=seen_s, seen=seen_s)
    return entry


def _derived_track(heatmap: Heatmap, index: int, history: np.ndarray) -> float | None:
    """Bearing from the latest earlier position at least 20 s older (and at most 180 s)."""
    now_ms = int(heatmap.time_ms[index])
    for earlier in history[::-1]:
        gap = now_ms - int(heatmap.time_ms[earlier])
        if gap < _TRACK_MIN_GAP_MS:
            continue
        if gap > _TRACK_MAX_GAP_MS:
            return None
        start = (heatmap.lat_e6[earlier] / 1e6, heatmap.lon_e6[earlier] / 1e6)
        end = (heatmap.lat_e6[index] / 1e6, heatmap.lon_e6[index] / 1e6)
        if distance_nm(*start, *end) < _TRACK_MIN_NM:
            return None
        return round(initial_bearing_deg(*start, *end), 1)
    return None


def point_query(url: str) -> tuple[float, float, float]:
    match = _POINT_URL.search(urlsplit(url).path)
    if match is None:
        raise ValueError(f"not an adsb.lol point URL: {url}")
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def heatmap_slots(spans: Sequence[tuple[datetime, datetime]]) -> list[datetime]:
    """Start of every half-hour heatmap the spans need (the step at a span's end reads the
    half-hour before it)."""
    slots: set[datetime] = set()
    for start, end in spans:
        at = start.replace(minute=start.minute - start.minute % 30, second=0, microsecond=0)
        while at < end:
            slots.add(at)
            at += timedelta(minutes=30)
    return sorted(slots)


def adsb_steps(
    spans: Sequence[tuple[datetime, datetime]], start: datetime, end: datetime
) -> tuple[list[datetime], list[datetime]]:
    """``(answer times, gap times)``: an answer every 60 s inside each span (from a minute
    after it opens, so the heatmap holds a minute of positions), and a gap marker at the
    window start when no span covers it and a minute after each span closes."""
    answers: set[datetime] = set()
    for first, last in spans:
        at = first + ADSB_STEP
        while at <= last:
            if start <= at <= end:
                answers.add(at)
            at += ADSB_STEP
    gaps = {last + ADSB_STEP for _, last in spans if last + ADSB_STEP <= end}
    if not answers or min(answers) > start:
        gaps.add(start)
    return sorted(answers), sorted(gaps - answers)


# --- context feeds: probe the case for the URLs its pollers request, then fill them --------


@dataclass(frozen=True)
class Request:
    feed: FeedId
    url: str
    at: datetime
    found: bool


class _LoggingReplaySource(ReplaySource):
    """The case's ``ReplaySource``, noting every URL asked for and whether the case had it."""

    def __init__(self, case_dir: Path, case: ReplayCase) -> None:
        super().__init__(case_dir, case)
        self.requests: list[Request] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: dict[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        try:
            result = await super().fetch(url, feed=feed, params=params)
        except FetchError:
            self.requests.append(Request(feed, full_url, timeutil.now(), found=False))
            raise
        self.requests.append(Request(feed, full_url, timeutil.now(), found=True))
        return result


class _EveryFeed:
    """Not a ``ReplaySource``, so the runtime also polls the feeds the case lacks: their
    URLs are what a backfill must fill."""

    def __init__(self, inner: _LoggingReplaySource) -> None:
        self._inner = inner

    async def fetch(
        self, url: str, *, feed: FeedId, params: dict[str, str] | None = None
    ) -> FetchResult:
        return await self._inner.fetch(url, feed=feed, params=params)

    async def aclose(self) -> None:
        await self._inner.aclose()


@asynccontextmanager
async def replay_runtime(
    data_dir: Path, case: ReplayCase, *, every_feed: bool
) -> AsyncIterator[tuple[Runtime, _LoggingReplaySource]]:
    """A REPLAY runtime on ``case`` (stub LLM, throwaway store) with a logging source."""
    with tempfile.TemporaryDirectory(prefix="tephra-probe-") as tmp:
        settings = Settings(
            _env_file=None,
            llm="stub",
            mode=RunMode.REPLAY,
            replay_case=case.case_id,
            data_dir=data_dir,
            store="sqlite",
            sqlite_path=Path(tmp) / "probe.sqlite3",
            cache_dir=Path(tmp) / "cache",
            region=case.region,
        )
        runtime = await create_runtime(settings)
        source = _LoggingReplaySource(case_path(data_dir, case.case_id), case)
        runtime.source = _EveryFeed(source) if every_feed else source
        try:
            yield runtime, source
        finally:
            await runtime.aclose()


async def tick_through(
    runtime: Runtime,
    times: Sequence[datetime],
    after_tick: Callable[[Runtime, datetime], Any] | None = None,
) -> None:
    """Tick the runtime at each time in order on a fixed clock."""
    clock = timeutil.FixedClock(times[0])
    with timeutil.use_clock(clock):
        for at in times:
            clock.set(at)
            await runtime.tick(reason="probe")
            if after_tick is not None:
                await after_tick(runtime, at)


def probe_times(
    start: datetime, end: datetime, every: timedelta, spans: Sequence[tuple[datetime, datetime]]
) -> list[datetime]:
    """Every ``every`` across the window, and every minute inside the ADS-B spans, where the
    flights near the cone (and so the alternates asked for) change from minute to minute."""
    times: set[datetime] = set()
    at = start
    while at <= end:
        times.add(at)
        at += every
    for first, last in spans:
        at = first
        while at <= last:
            if start <= at <= end:
                times.add(at)
            at += ADSB_STEP
    return sorted(times)


async def missing_urls(
    data_dir: Path, case: ReplayCase, times: Sequence[datetime], feeds: Iterable[FeedId]
) -> dict[str, FeedId]:
    """URLs of ``feeds`` that replay ticks at ``times`` ask for and the case lacks."""
    wanted = set(feeds)
    quiet = logging.getLogger("tephra")
    level = quiet.level
    quiet.setLevel(logging.ERROR)  # every lacking URL logs a warning; the caller fills them
    try:
        async with replay_runtime(data_dir, case, every_feed=True) as (runtime, source):
            await tick_through(runtime, times)
    finally:
        quiet.setLevel(level)
    return {
        request.url: request.feed
        for request in source.requests
        if request.feed in wanted and not request.found
    }


@dataclass
class ContextFiller:
    """Fills one requested URL of a context feed across the whole case window."""

    case_dir: Path
    start: datetime
    end: datetime
    fetcher: ArchiveFetcher
    metar_source: str
    adsb_spans: Sequence[tuple[datetime, datetime]]
    cache_dir: Path | None
    adsb_max_bytes: int
    _metars: list[IemMetar] | None = field(default=None, init=False)
    _heatmap: Heatmap | None = field(default=None, init=False)

    def records(self, feed: FeedId, url: str) -> list[ReplayRecord]:
        if feed is FeedId.TAF or (feed is FeedId.METAR and self.metar_source == "awc"):
            return self._awc_history(feed, url)
        if feed is FeedId.METAR:
            return self._iem_metars(url)
        if feed is FeedId.WINDS:
            return self._winds(url)
        if feed is FeedId.ADSB:
            return self._adsb(url)
        raise ValueError(f"{feed.value} is not a context feed")

    def _hours(self) -> list[datetime]:
        first = self.start.replace(minute=0, second=0, microsecond=0)
        count = int((self.end - first) / timedelta(hours=1)) + 1
        return [first + timedelta(hours=n) for n in range(count)]

    def _awc_history(self, feed: FeedId, url: str) -> list[ReplayRecord]:
        records: list[ReplayRecord] = []
        for at in self._hours():
            try:
                status, content = self.fetcher.get(awc_history_url(url, at))
            except RuntimeError as exc:
                print(f"    {feed.value} {at:%Y-%m-%d %H:%MZ}: {exc}")
                continue
            records.append(_store(self.case_dir, feed, url, at, content, status, JSON_TYPE))
        return records

    def _iem_metars(self, url: str) -> list[ReplayRecord]:
        stations = dict(parse_qsl(urlsplit(url).query)).get("ids", "").split(",")
        metars = self._iem_archive()
        records: list[ReplayRecord] = []
        at = self.start.replace(
            minute=self.start.minute - self.start.minute % 30, second=0, microsecond=0
        )
        while at <= self.end:
            content = metar_response(metars, stations, at)
            records.append(_store(self.case_dir, FeedId.METAR, url, at, content, 200, JSON_TYPE))
            at += METAR_STEP
        return records

    def _iem_archive(self) -> list[IemMetar]:
        """Every catalogue airport's METARs, in one request: the stations a replay asks
        for change with the flights it tracks."""
        if self._metars is None:
            catalogue = json.loads((PROJECT_ROOT / "data" / "airports.json").read_text())
            stations = [airport["icao"] for airport in catalogue["airports"]]
            url = iem_asos_url(stations, self.start - timedelta(hours=12), self.end)
            _, content = self.fetcher.get(url)
            self._metars = parse_iem_csv(content.decode("utf-8", errors="replace"))
            print(f"    IEM ASOS: {len(self._metars)} METARs for {len(stations)} airports")
        return self._metars

    def _winds(self, url: str) -> list[ReplayRecord]:
        records: list[ReplayRecord] = []
        for at in self._hours():
            try:
                status, content = self.fetcher.get(historical_wind_url(url, at))
            except RuntimeError as exc:
                print(f"    winds {at:%Y-%m-%d %H:%MZ}: {exc}")
                continue
            records.append(_store(self.case_dir, FeedId.WINDS, url, at, content, status, JSON_TYPE))
        return records

    def _adsb(self, url: str) -> list[ReplayRecord]:
        lat, lon, radius_nm = point_query(url)
        heatmap = self._heatmaps()
        answers, gaps = adsb_steps(self.adsb_spans, self.start, self.end)
        records = [
            _store(
                self.case_dir,
                FeedId.ADSB,
                url,
                at,
                _json_bytes(point_response(heatmap, lat, lon, radius_nm, at)),
                200,
                "application/json",
            )
            for at in answers
        ]
        records += [_store(self.case_dir, FeedId.ADSB, url, at, b"", 204, None) for at in gaps]
        return records

    def _heatmaps(self) -> Heatmap:
        if self._heatmap is None:
            slots = heatmap_slots(self.adsb_spans)
            urls = [
                ADSB_HEATMAP_URL.format(at=at, index=at.hour * 2 + at.minute // 30) for at in slots
            ]
            planned = sum(self.fetcher.head_size(url) or 0 for url in urls)
            print(f"    {len(urls)} adsb.lol heatmaps, {planned / 1e6:.0f} MB to fetch at most")
            if planned > self.adsb_max_bytes:
                raise SystemExit(
                    f"the ADS-B spans need {planned / 1e6:.0f} MB of heatmaps, over the "
                    f"{self.adsb_max_bytes / 1e6:.0f} MB limit (--adsb-max-mb)"
                )
            self._heatmap = join_heatmaps(
                [self._heatmap_part(url, at) for url, at in zip(urls, slots, strict=True)]
            )
        return self._heatmap

    def _heatmap_part(self, url: str, at: datetime) -> Heatmap:
        """One decoded heatmap; with a cache directory, the decoded positions are kept (a few
        MB) instead of the 10-30 MB file."""
        path = self.cache_dir / "heatmap" / f"{at:%Y%m%d_%H%M}.npz" if self.cache_dir else None
        if path is not None and path.is_file():
            return _load_heatmap(path)
        _, raw = self.fetcher.get(url, cache=False)
        heatmap = decode_heatmap(raw)
        if path is not None:
            _save_heatmap(path, heatmap)
        return heatmap


def _save_heatmap(path: Path, heatmap: Heatmap) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    reports = [
        (addr, when, text) for addr, items in heatmap.callsigns.items() for when, text in items
    ]
    np.savez_compressed(
        path,
        time_ms=heatmap.time_ms,
        addr=heatmap.addr,
        lat_e6=heatmap.lat_e6,
        lon_e6=heatmap.lon_e6,
        alt=heatmap.alt,
        gs=heatmap.gs,
        callsigns=np.array(json.dumps(reports)),
    )


def _load_heatmap(path: Path) -> Heatmap:
    with np.load(path) as data:
        callsigns: dict[int, list[tuple[int, str]]] = {}
        for addr, when, text in json.loads(str(data["callsigns"])):
            callsigns.setdefault(int(addr), []).append((int(when), text))
        return Heatmap(
            time_ms=data["time_ms"],
            addr=data["addr"],
            lat_e6=data["lat_e6"],
            lon_e6=data["lon_e6"],
            alt=data["alt"],
            gs=data["gs"],
            callsigns=callsigns,
        )


def fill_context(
    args: argparse.Namespace, case_dir: Path, records: list[ReplayRecord], notes: str
) -> list[ReplayRecord]:
    """Probe the case for the context feeds' URLs and fill them until none is missing."""
    feeds = [FeedId(name) for name in args.context]
    every = timedelta(minutes=args.probe_minutes)
    times = probe_times(args.start, args.end, every, args.adsb_span)
    fetcher = ArchiveFetcher(args.cache_dir)
    filler = ContextFiller(
        case_dir=case_dir,
        start=args.start,
        end=args.end,
        fetcher=fetcher,
        metar_source=args.metar_source,
        adsb_spans=args.adsb_span,
        cache_dir=args.cache_dir,
        adsb_max_bytes=args.adsb_max_mb * 1_000_000,
    )
    filled: set[str] = set()
    try:
        for round_number in range(1, MAX_PROBE_ROUNDS + 1):
            case = write_manifest(args, case_dir, records, notes, window=(args.start, args.end))
            print(f"  probe {round_number}: {len(times)} replay ticks")
            missing = asyncio.run(missing_urls(args.data_dir, case, times, feeds))
            todo = {url: feed for url, feed in missing.items() if url not in filled}
            if not todo:
                break
            for url, feed in sorted(todo.items(), key=lambda item: (item[1].value, item[0])):
                print(f"    filling {feed.value}: {url}")
                records += filler.records(feed, url)
                filled.add(url)
        else:
            print(f"warning: URLs still missing after {MAX_PROBE_ROUNDS} probes")
    finally:
        fetcher.close()
        print(f"  fetched {fetcher.bytes_fetched / 1e6:.1f} MB for the context feeds")
    return records


# --- case files ---------------------------------------------------------------------------


def _store(
    case_dir: Path,
    feed: FeedId,
    url: str,
    at: datetime,
    content: bytes,
    status_code: int,
    content_type: str | None,
) -> ReplayRecord:
    """Write ``content`` once under ``raw/<feed>/`` (named by its hash) and return its record."""
    if _BOM_COPYRIGHT in content:
        raise SystemExit(f"refusing BoM FTP material for {url}: BoM's terms forbid supplying it")
    digest = hashlib.sha256(content).hexdigest()
    kind = (content_type or "").split(";")[0].strip()
    suffix = {"application/json": ".json", "text/html": ".html"}.get(kind, ".txt")
    relative = Path("raw") / feed.value / f"{digest[:20]}{suffix}"
    target = case_dir / relative
    if not target.is_file():
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


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, separators=(",", ":")).encode()


def write_manifest(
    args: argparse.Namespace,
    case_dir: Path,
    records: list[ReplayRecord],
    notes: str,
    window: tuple[datetime, datetime] | None = None,
) -> ReplayCase:
    if not records:
        raise SystemExit("nothing was recorded; no manifest written")
    times = [record.fetched_at for record in records]
    recorded_from, recorded_to = window or (min(times), max(times))
    case = ReplayCase(
        case_id=args.case,
        label=args.label,
        recorded_from=recorded_from,
        recorded_to=recorded_to,
        region=args.region,
        volcano_ids=args.volcano or [],
        notes=notes,
        records=sorted(records, key=lambda record: (record.fetched_at, record.url)),
    )
    (case_dir / "manifest.json").write_text(case.model_dump_json(indent=2))
    return case


def _clear_case(case_dir: Path) -> None:
    """Remove a case's manifest and raw files before it is rebuilt from scratch."""
    shutil.rmtree(case_dir / "raw", ignore_errors=True)
    (case_dir / "manifest.json").unlink(missing_ok=True)


# --- probe: what a replay shows at chosen times ---------------------------------------------


async def probe(
    data_dir: Path,
    case: ReplayCase,
    report_at: Sequence[datetime],
    every: timedelta,
    begin: datetime | None,
) -> None:
    """Tick the case every ``every`` from ``begin`` (default: the first report time) and print
    the picture at each report time, plus a line whenever a flight becomes exposed or clear and
    whenever a draft is created."""
    first = min(report_at) if begin is None else begin
    times = sorted({*probe_times(first, max(report_at), every, []), *report_at})
    exposed: set[str] = set()
    drafted: set[str] = set()

    async def after_tick(runtime: Runtime, at: datetime) -> None:
        nonlocal exposed
        stamp = f"{at:%d %H:%MZ}"
        for flight_id in sorted(runtime.exposed.keys() - exposed):
            print(f"{stamp} exposed: {_flight_text(runtime.exposed[flight_id])}")
        for flight_id in sorted(exposed - runtime.exposed.keys()):
            print(f"{stamp} clear: {flight_id}")
        exposed = set(runtime.exposed)
        for draft in await list_advisories(runtime.store, status=AdvisoryStatus.DRAFT, limit=200):
            if draft.id not in drafted:
                drafted.add(draft.id)
                print(f"{stamp} draft: {_draft_text(draft)}")
        if at in report_at:
            print(await describe(runtime, at))

    async with replay_runtime(data_dir, case, every_feed=False) as (runtime, source):
        await tick_through(runtime, times, after_tick)
    missing = sorted(
        {(request.feed.value, request.url) for request in source.requests if not request.found}
    )
    for feed, url in missing:
        print(f"not in the case: {feed} {url}")


def _flight_text(flight: Any) -> str:
    where = "inside" if flight.inside_now else f"entry in {flight.minutes_to_entry} min"
    level = "FL?" if flight.alt_baro_ft is None else f"FL{round(flight.alt_baro_ft / 100):03d}"
    who = f"{flight.proxy_flight} {flight.callsign or '-'} {flight.hex}"
    return f"{who} {level} {where} ({flight.volcano_id})"


def _draft_text(draft: Any) -> str:
    return (
        f"{draft.proxy_flight} {draft.callsign or '-'} {draft.action.value} ({draft.volcano_name})"
    )


async def describe(runtime: Runtime, at: datetime) -> str:
    drafts = await list_advisories(runtime.store, status=AdvisoryStatus.DRAFT, limit=200)
    lines = [f"== {timeutil.to_iso(at)}"]
    for feed, state in sorted(runtime.live.health.items(), key=lambda item: item[0].value):
        error = f" ({state.last_error})" if state.last_error else ""
        lines.append(
            f"  feed {feed.value}: {state.status.value}, {state.record_count} records{error}"
        )
    for vid, reasons in sorted(runtime.live.active.items()):
        lines.append(f"  active {vid}: {'; '.join(reasons)}")
    for vid, situation in sorted(runtime.situations.items()):
        counts = (
            f"{len(situation.sigmets)} SIGMET, {len(situation.vaas)} VAA, "
            f"{len(situation.vonas)} VONA, {len(situation.official_layers)} official layers"
        )
        lines.append(f"  {situation.volcano.name}: {counts}")
        for item in situation.discrepancies:
            lines.append(f"    {item.kind.value}: {item.summary}")
        cone = runtime.cones.get(vid)
        if cone is not None:
            lines.append(
                f"    cone {cone.label} FL{cone.base_ft // 100:03d}-FL{cone.top_ft // 100:03d} "
                f"{cone.horizon_h:g} h, {len(cone.official_source_ids)} official sources"
            )
    lines += [f"  exposed {_flight_text(flight)}" for flight in runtime.exposed.values()]
    lines += [f"  draft {_draft_text(draft)}" for draft in drafts]
    return "\n".join(lines)


# --- command line -------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record or rebuild a labelled TEPHRA replay case (see the module docstring)."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    noaaport = sub.add_parser(
        "noaaport", help="stream IEM NOAAPort day files and keep their VA bulletins"
    )
    noaaport.add_argument("--day", action="append", required=True, type=_day, help="YYYY-MM-DD")
    noaaport.add_argument("--out", required=True, type=Path, help="directory for <day>.jsonl")
    noaaport.add_argument("--last-hour", type=int, default=23, help="stop after this UTC hour")
    for name, text in (
        ("live", "record the live feeds for a while"),
        ("backfill", "rebuild a past window from archives"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("--case", required=True, help="case id: lowercase letters, digits, dashes")
        p.add_argument("--label", required=True, help="human label shown on the REPLAY banner")
        p.add_argument("--region", default="java_bali")
        p.add_argument("--volcano", action="append", help="volcano id to tag (repeatable)")
        p.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
        p.add_argument(
            "--force",
            action="store_true",
            help="overwrite an existing case (backfill: from scratch)",
        )
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
    back.add_argument(
        "--sigmet-source",
        choices=("awc", "census", "noaaport", "none"),
        help="awc: date= snapshots every --step-minutes (30 days of history); census: the "
        "census's hourly snapshots; noaaport: raw bulletins in AWC's JSON (a reconstruction). "
        "Default: census with --census-dir, else awc",
    )
    back.add_argument("--step-minutes", type=int, default=60, help="AWC snapshot spacing")
    back.add_argument(
        "--fir", action="append", help=f"FIRs for noaaport SIGMETs ({', '.join(DEFAULT_FIRS)})"
    )
    back.add_argument("--census-dir", type=Path, help="research census (manifest.tsv + raw/)")
    back.add_argument(
        "--noaaport-dir",
        type=Path,
        help="bulletins saved by the noaaport command: Darwin VAAs (and SIGMETs with "
        "--sigmet-source noaaport) come from here",
    )
    back.add_argument(
        "--with-vona",
        action="store_true",
        help="also import the census's saved MAGMA VONA list pages (needs --census-dir)",
    )
    back.add_argument(
        "--context",
        type=lambda text: [part.strip() for part in text.split(",") if part.strip()],
        default=[],
        help="context feeds to fill after probing the case: any of taf,metar,winds,adsb",
    )
    back.add_argument("--metar-source", choices=("awc", "iem"), default="awc")
    back.add_argument(
        "--adsb-span",
        action="append",
        type=_span,
        default=[],
        help="START/END of an ADS-B span rebuilt from adsb.lol heatmaps (repeatable)",
    )
    back.add_argument("--adsb-max-mb", type=int, default=700, help="heatmap download limit")
    back.add_argument("--probe-minutes", type=int, default=30, help="probe tick spacing")
    back.add_argument("--cache-dir", type=Path, help="keep fetched archive answers here")
    probe_cmd = sub.add_parser("probe", help="replay ticks at chosen times; print the picture")
    probe_cmd.add_argument("--case", required=True)
    probe_cmd.add_argument("--at", action="append", required=True, type=_utc)
    probe_cmd.add_argument(
        "--from", dest="begin", type=_utc, help="first tick (default: first --at)"
    )
    probe_cmd.add_argument("--every", type=int, default=1, help="minutes between ticks")
    probe_cmd.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    args = parser.parse_args(argv)
    if args.command in ("noaaport", "probe"):
        return args
    if not _CASE_ID.match(args.case):
        parser.error("--case must be 3-64 chars of lowercase letters, digits and dashes")
    if args.command == "backfill":
        _check_backfill(parser, args)
    return args


def _check_backfill(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.end <= args.start:
        parser.error("--end must be after --start")
    if args.sigmet_source is None:
        args.sigmet_source = "census" if args.census_dir else "awc"
    if args.with_vona and args.census_dir is None:
        parser.error("--with-vona needs --census-dir: VONAs are never fetched from MAGMA")
    if args.sigmet_source == "census" and args.census_dir is None:
        parser.error("--sigmet-source census needs --census-dir")
    if args.sigmet_source == "noaaport" and args.noaaport_dir is None:
        parser.error("--sigmet-source noaaport needs --noaaport-dir")
    unknown = set(args.context) - {feed.value for feed in CONTEXT_FEEDS}
    if unknown:
        parser.error(f"--context takes taf, metar, winds, adsb (not {', '.join(sorted(unknown))})")
    if "adsb" in args.context and not args.adsb_span:
        parser.error("--context adsb needs at least one --adsb-span")
    if "taf" in args.context or ("metar" in args.context and args.metar_source == "awc"):
        oldest = datetime.now(UTC) - timedelta(days=AWC_HISTORY_DAYS)
        if args.start < oldest:
            parser.error("AWC keeps 30 days of TAF/METAR history; use --metar-source iem")
    args.fir = args.fir or list(DEFAULT_FIRS)


def backfill(args: argparse.Namespace, case_dir: Path) -> tuple[list[ReplayRecord], str]:
    """The product legs (SIGMET, Darwin VAA, VONA) and their part of the manifest notes."""
    records: list[ReplayRecord] = []
    parts: list[str] = []
    saved = read_census(args.census_dir) if args.census_dir else []
    bulletins = read_noaaport_dir(args.noaaport_dir) if args.noaaport_dir else []
    if args.sigmet_source == "census":
        records += import_census_sigmets(saved, args.start, args.end, case_dir)
        parts.append(
            "VA SIGMETs from the hourly aviationweather.gov date= snapshots the research "
            "census saved (real AWC JSON, research/data/census)"
        )
    elif args.sigmet_source == "awc":
        fetcher = ArchiveFetcher(args.cache_dir)
        try:
            step = timedelta(minutes=args.step_minutes)
            records += fetch_awc_sigmets(fetcher, args.start, args.end, step, case_dir)
        finally:
            fetcher.close()
        parts.append(
            f"VA SIGMETs from aviationweather.gov date= snapshots every {args.step_minutes} min"
        )
    elif args.sigmet_source == "noaaport":
        records += import_noaaport_sigmets(bulletins, args.fir, args.start, args.end, case_dir)
        parts.append(_NOAAPORT_SIGMET_NOTE.format(firs=", ".join(args.fir)))
    if bulletins:
        records += import_darwin(bulletins, args.start, args.end, case_dir)
        parts.append(_DARWIN_NOTE)
        parts += noaaport_notes(bulletins, args.start, args.end)
    if args.with_vona:
        records += import_census_vona_pages(saved, case_dir)
        parts.append(
            "MAGMA VONA list pages as the research census fetched them on 9 Oct 2026; the "
            "poller reads only notices issued before the replay clock, from their list cards"
        )
    return records, "Reconstructed from archives, not recorded live. " + " ".join(
        f"{part}." for part in parts
    )


def noaaport_notes(bulletins: Sequence[Bulletin], start: datetime, end: datetime) -> list[str]:
    """What the archive lacks in the window: silent spans and missing Darwin advisories."""
    notes = [
        f"IEM's NOAAPort archive holds no bulletin between {_when(before)} and {_when(after)}; "
        "SIGMETs and VAAs issued then are missing from this case"
        for before, after in archive_gaps(bulletins, start, end)
    ]
    vaas = darwin_vaas(bulletins)
    replayed = [(at, vaa) for at, vaa in retransmissions(vaas) if at <= end]
    if replayed:
        first, last = min(at for at, _ in replayed), max(at for at, _ in replayed)
        notes.append(
            f"Darwin bulletins that NOAAPort re-sent between {_when(first)} and {_when(last)} "
            f"after newer ones on the same slots ({len(replayed)}) are left out, because a slot "
            "holds Darwin's newest advisory on its heading"
        )
    unheld = unheld_slots(darwin_slot_states(vaas, start, end), start)
    if unheld:
        names = ", ".join(f"FVAU{slot:02d}" for slot in unheld)
        notes.append(
            f"The streamed days hold no bulletin for {names} before the window, so each starts "
            "with an empty 204 record, which the poller reads as unavailable"
        )
    issued = [vaa for _, vaa in vaas if start <= vaa.dtg <= end]
    missing = [
        f"{volcano} {', '.join(f'{start.year}/{number}' for number in gaps)}"
        for volcano, (_, _, gaps) in advisory_runs(issued, (vaa for _, vaa in vaas)).items()
        if gaps
    ]
    if missing:
        notes.append(f"Darwin advisories missing from the archive: {'; '.join(missing)}")
    return notes


def _when(at: datetime) -> str:
    return at.strftime("%H:%MZ on %d %b %Y").replace(" 0", " ", 1)


_NOAAPORT_SIGMET_NOTE: Final = (
    "VA SIGMETs ({firs}) from the IEM NOAAPort raw-text archive (public domain; bulletins "
    "issued by BMKG and BoM and relayed by NWS). AWC's JSON for these dates no longer exists, "
    "so the isigmet JSON is a reconstruction around the raw bulletins: each bulletin is "
    "wrapped in the fields the parser reads (rawSigmet, hazard, icaoId, firId, firName, "
    "seriesId, validTimeFrom/To from the VALID group, receiptTime from the heading or the "
    "archive hour), and geometry, levels and movement are left for the parser to read from "
    "rawSigmet. A SIGMET with a forecast polygon also gets an F record, as AWC makes. CNL "
    "SIGMET bulletins are listed as cancelled records and end the SIGMET they cancel at "
    "their start, as AWC shortens validTimeTo. A list is stored at the window start and at "
    "each later arrival; copies relayed twice with different line wrapping are merged"
)
_DARWIN_NOTE: Final = (
    "Darwin VAA bulletins (FVAU01-10 ADRM) from the IEM NOAAPort archive, the public-domain "
    "relay whose files NWS serves on tgftp: each is stored under the tgftp slot of its "
    "heading at the later of its DTG and its arrival, with every slot's last bulletin before "
    "the window, and copies relayed twice are merged. Nothing comes from BoM's FTP server"
)
_CONTEXT_NOTES: Final = {
    "taf": (
        "TAFs from aviationweather.gov date= history (real AWC JSON), hourly, under the "
        "station lists the replay's pollers request (found by probing the case)"
    ),
    "metar-awc": (
        "METARs from aviationweather.gov date= history (real AWC JSON), hourly, under the "
        "station lists the replay's pollers request (found by probing the case)"
    ),
    "metar-iem": (
        "METARs from the IEM ASOS archive (public domain), converted to AWC's METAR JSON by "
        "TEPHRA, a reconstruction: icaoId, obsTime, reportTime, rawOb (IEM's text, without "
        "AWC's METAR/SPECI prefix), visib (statute miles as AWC renders them), wxString, "
        "clouds, vertVis and fltCat are decoded from the text. Every 30 min each response "
        "holds the latest METAR per station, under the station lists the pollers request"
    ),
    "winds": (
        "Pressure-level winds from the Open-Meteo Historical Forecast API (CC BY 4.0, "
        "Weather data by Open-Meteo.com), hourly, under the live winds URLs: each response "
        "is the archive's answer for the same fields from one hour before to 23 hours after "
        "its time (start_hour/end_hour in place of past_hours/forecast_hours). These are "
        "short-range model runs stitched together, not the forecast that was current then"
    ),
    "adsb": (
        "ADS-B for {spans} reconstructed from adsb.lol's globe_history heatmaps (ODbL 1.0, "
        "Aircraft: adsb.lol), not fetched from its API: every 60 s, one /v2/point response "
        "per query point the replay requests, holding each aircraft whose latest heatmap "
        "position in the last 60 s lies inside the radius. hex, flight, lat, lon, alt_baro "
        "(25 ft steps; the heatmap falls back to geometric altitude when baro is missing) "
        "and gs come from the heatmap; track is derived from successive positions and "
        "seen_pos/seen from the position's age; type, registration and selected altitude "
        "are absent. Outside the spans each point holds an empty 204 record, so the replay "
        "shows ADS-B as failing rather than freezing or leaking positions"
    ),
}


def context_notes(args: argparse.Namespace) -> list[str]:
    notes: list[str] = []
    for feed in args.context:
        key = f"metar-{args.metar_source}" if feed == "metar" else feed
        spans = ", ".join(
            f"{timeutil.to_iso(first)[:16]}Z to {timeutil.to_iso(last)[:16]}Z"
            for first, last in args.adsb_span
        )
        notes.append(_CONTEXT_NOTES[key].format(spans=spans))
    return notes


def absent_note(records: Iterable[ReplayRecord]) -> str:
    held = {record.feed for record in records}
    names = [FEED_LABELS[feed] for feed in FeedId if feed not in held]
    return f"Not in this case, and shown as such: {', '.join(names)}." if names else ""


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "noaaport":
        for day in args.day:
            stream_noaaport_day(day, args.out, last_hour=args.last_hour)
        return 0
    if args.command == "probe":
        case = load_case(args.data_dir, args.case)
        asyncio.run(probe(args.data_dir, case, args.at, timedelta(minutes=args.every), args.begin))
        return 0
    case_dir = case_path(args.data_dir, args.case)
    if not args.force and any((case_dir / name).exists() for name in ("manifest.json", "raw")):
        raise SystemExit(f"{case_dir} already holds a case; pass --force to overwrite it")
    case_dir.mkdir(parents=True, exist_ok=True)
    if args.command == "live":
        records = asyncio.run(record_live(args, case_dir))
        notes = f"Recorded live from public feeds for {args.minutes:g} min."
        case = write_manifest(args, case_dir, records, notes)
    else:
        _clear_case(case_dir)
        records, notes = backfill(args, case_dir)
        if args.context:
            records = fill_context(args, case_dir, records, notes)
        context = [f"{note}." for note in context_notes(args)]
        notes = " ".join([notes, *context, absent_note(records)]).strip()
        case = write_manifest(args, case_dir, records, notes, window=(args.start, args.end))
    print(f"wrote {case_dir / 'manifest.json'} ({len(case.records)} responses)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
