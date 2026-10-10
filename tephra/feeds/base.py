"""Polite HTTP access to public feeds, with provenance and last-good caching.

Feed modules never call httpx directly; they call ``source.fetch(url, feed=..., params=...)``
on a :class:`Source`. Live runs use :class:`HttpSource`; REPLAY swaps in the recorded
source from ``tephra.replay.cases``; ``scripts/record_replay.py`` wraps a live source in
:class:`RecordingSource`. TEPHRA only ever issues GET requests to public feeds.

Callers must build ``params`` in a fixed key order: the final URL string is the cache key
and the replay lookup key.
"""

import asyncio
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable
from urllib.parse import urlsplit

import httpx

from tephra.models import FeedId, Provenance, ReplayCase, ReplayRecord
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes, sha256_text

if TYPE_CHECKING:
    from tephra.config import Settings

__all__ = [
    "USER_AGENT",
    "FetchError",
    "FetchResult",
    "HttpSource",
    "LastGoodCache",
    "RecordingSource",
    "Source",
    "build_url",
]

USER_AGENT = "TEPHRA/0.1 (+https://github.com/officialasishkumar/tephra)"
DEFAULT_HOST_INTERVAL_S = 0.5
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
RETRYABLE_STATUS = frozenset({408, 420, 425, 429, 500, 502, 503, 504})
THROTTLE_STATUS = frozenset({420, 429})
MAX_THROTTLE_WAIT_S = 30.0
CACHE_MAX_AGE_S = 48 * 3600
UNCACHED_FEEDS = frozenset({FeedId.HSD, FeedId.FRAMES})
"""Raw HSD segments and satellite frames are fetched once per scan under per-scan URLs: a
last-good copy is never re-read, and frames alone would hold ~400 MiB at the 48 h retention
(Cloud Run's filesystem is memory)."""


class FetchError(RuntimeError):
    """A fetch failed and no last-good copy exists."""

    def __init__(self, url: str, feed: FeedId, reason: str) -> None:
        super().__init__(f"{feed.value}: {reason} ({url})")
        self.url = url
        self.feed = feed
        self.reason = reason


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Raw bytes of one response plus what is needed to build a :class:`Provenance`.

    ``stale`` results come from the last-good cache after a live failure: ``fetched_at``
    is when the cached copy was fetched and ``error`` says why the live fetch failed.
    """

    feed: FeedId
    url: str
    status_code: int
    content: bytes = field(repr=False)
    content_type: str | None
    fetched_at: datetime
    sha256: str
    from_cache: bool = False
    stale: bool = False
    stale_age_s: int | None = None
    replay: bool = False
    error: str | None = None

    def text(self, encoding: str | None = None) -> str:
        return self.content.decode(encoding or _charset(self.content_type), errors="replace")

    def json(self) -> Any:
        return json.loads(self.content)

    def provenance(
        self,
        source_id: str,
        *,
        issued_at: datetime | None = None,
        valid_from: datetime | None = None,
        valid_to: datetime | None = None,
    ) -> Provenance:
        return Provenance(
            source_id=source_id,
            feed=self.feed,
            url=self.url,
            fetched_at=self.fetched_at,
            issued_at=issued_at,
            valid_from=valid_from,
            valid_to=valid_to,
            sha256=self.sha256,
            stale=self.stale,
            stale_age_s=self.stale_age_s,
            replay=self.replay,
        )


@runtime_checkable
class Source(Protocol):
    """Anything that can answer a GET for a feed: live HTTP, a recorder, or a replay case."""

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult: ...

    async def aclose(self) -> None: ...


def build_url(url: str, params: Mapping[str, str] | None = None) -> str:
    """The exact URL string fetched (and used as cache and replay key)."""
    if not params:
        return url
    return str(httpx.URL(url).copy_merge_params(dict(params)))


class LastGoodCache:
    """Last successful response per URL on local disk, kept for 48 hours."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._saves = 0

    def save(self, result: FetchResult) -> None:
        body_path, meta_path = self._paths(result.url)
        self._root.mkdir(parents=True, exist_ok=True)
        meta = {
            "url": result.url,
            "feed": result.feed.value,
            "status_code": result.status_code,
            "content_type": result.content_type,
            "fetched_at": timeutil.to_iso(result.fetched_at),
            "sha256": result.sha256,
        }
        _atomic_write(body_path, result.content)
        _atomic_write(meta_path, json.dumps(meta).encode())
        self._saves += 1
        if self._saves % 200 == 0:
            self.prune(CACHE_MAX_AGE_S)

    def load(self, url: str, feed: FeedId) -> FetchResult | None:
        body_path, meta_path = self._paths(url)
        try:
            meta = json.loads(meta_path.read_bytes())
            content = body_path.read_bytes()
        except (OSError, ValueError):
            return None
        if meta.get("url") != url or sha256_bytes(content) != meta.get("sha256"):
            return None
        return FetchResult(
            feed=feed,
            url=url,
            status_code=int(meta["status_code"]),
            content=content,
            content_type=meta.get("content_type"),
            fetched_at=timeutil.parse_iso(meta["fetched_at"]),
            sha256=meta["sha256"],
            from_cache=True,
        )

    def prune(self, max_age_s: float) -> None:
        cutoff = time.time() - max_age_s
        if not self._root.is_dir():
            return
        for path in self._root.iterdir():
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
            except OSError:
                continue

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = sha256_text(url)[:40]
        return self._root / f"{key}.body", self._root / f"{key}.json"


class _LiveFailure(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class HttpSource:
    """Live GETs with timeouts, retries, per-host spacing, 420/429 back-off and last-good.

    Requests to one host are serialised and spaced by that host's minimum interval
    (adsb.lol asks for at least one second between calls). Fetch times are wall-clock UTC
    even while a replay clock is installed (auto-replay keeps polling live SIGMETs).
    """

    def __init__(
        self,
        *,
        cache_dir: Path,
        timeout_s: float = 20.0,
        retries: int = 2,
        host_intervals_s: Mapping[str, float] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cache = LastGoodCache(cache_dir / "http")
        self._client = httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(timeout_s, connect=min(10.0, timeout_s)),
            follow_redirects=True,
            transport=transport,
        )
        self._retries = retries
        self._intervals: dict[str, float] = {"api.adsb.lol": 1.1, **(host_intervals_s or {})}
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_ready_at: dict[str, float] = {}
        self._clock = timeutil.SystemClock()

    @classmethod
    def from_settings(cls, settings: "Settings") -> "HttpSource":
        return cls(
            cache_dir=settings.cache_dir,
            timeout_s=settings.http_timeout_s,
            retries=settings.http_retries,
            host_intervals_s={"api.adsb.lol": settings.adsb_min_interval_s},
        )

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        full_url = build_url(url, params)
        try:
            response = await self._get_with_retries(full_url)
        except _LiveFailure as failure:
            return await self._fallback(full_url, feed, failure.reason)
        result = FetchResult(
            feed=feed,
            url=full_url,
            status_code=response.status_code,
            content=response.content,
            content_type=response.headers.get("content-type"),
            fetched_at=self._clock.now(),
            sha256=sha256_bytes(response.content),
        )
        if feed not in UNCACHED_FEEDS:
            await asyncio.to_thread(self._cache.save, result)
        return result

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get_with_retries(self, url: str) -> httpx.Response:
        host = urlsplit(url).hostname or ""
        reason = "not attempted"
        for attempt in range(self._retries + 1):
            response: httpx.Response | None = None
            async with self._lock(host):
                await self._wait_for_turn(host)
                pause = self._intervals.get(host, DEFAULT_HOST_INTERVAL_S)
                try:
                    response = await self._client.get(url)
                except httpx.HTTPError as exc:
                    reason = f"{type(exc).__name__}: {exc}"
                else:
                    if response.status_code in THROTTLE_STATUS:
                        pause = max(pause, _retry_after_s(response, 5.0 * (attempt + 1)))
                finally:
                    self._host_ready_at[host] = time.monotonic() + pause
            if response is not None:
                if response.is_success:
                    if len(response.content) > MAX_RESPONSE_BYTES:
                        raise _LiveFailure(f"response larger than {MAX_RESPONSE_BYTES} bytes")
                    return response
                reason = f"HTTP {response.status_code}"
                if response.status_code not in RETRYABLE_STATUS:
                    break
            if attempt < self._retries:
                await asyncio.sleep(min(2.0**attempt, 8.0))
        raise _LiveFailure(reason)

    async def _fallback(self, url: str, feed: FeedId, reason: str) -> FetchResult:
        cached = await asyncio.to_thread(self._cache.load, url, feed)
        if cached is None:
            raise FetchError(url, feed, reason)
        age = timeutil.age_s(cached.fetched_at, self._clock.now())
        return replace(cached, stale=True, stale_age_s=age, error=reason)

    def _lock(self, host: str) -> asyncio.Lock:
        lock = self._host_locks.get(host)
        if lock is None:
            lock = self._host_locks[host] = asyncio.Lock()
        return lock

    async def _wait_for_turn(self, host: str) -> None:
        delay = self._host_ready_at.get(host, 0.0) - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)


class RecordingSource:
    """Wraps a live source and writes every fresh response into a replay case directory.

    Cached (stale) answers are passed through but not recorded: a replay case holds only
    responses that were actually fetched during the recording window.
    """

    def __init__(self, inner: Source, case_dir: Path) -> None:
        self._inner = inner
        self._case_dir = case_dir
        self.records: list[ReplayRecord] = []

    async def fetch(
        self, url: str, *, feed: FeedId, params: Mapping[str, str] | None = None
    ) -> FetchResult:
        result = await self._inner.fetch(url, feed=feed, params=params)
        if not result.from_cache:
            await asyncio.to_thread(self._record, result)
        return result

    async def aclose(self) -> None:
        await self._inner.aclose()

    def manifest(
        self,
        *,
        case_id: str,
        label: str,
        region: str,
        volcano_ids: list[str] | None = None,
        notes: str | None = None,
    ) -> ReplayCase:
        if not self.records:
            raise ValueError("nothing was recorded")
        times = [record.fetched_at for record in self.records]
        return ReplayCase(
            case_id=case_id,
            label=label,
            recorded_from=min(times),
            recorded_to=max(times),
            region=region,
            volcano_ids=volcano_ids or [],
            notes=notes,
            records=sorted(self.records, key=lambda record: record.fetched_at),
        )

    def write_manifest(self, case: ReplayCase) -> Path:
        path = self._case_dir / "manifest.json"
        _atomic_write(path, case.model_dump_json(indent=2).encode())
        return path

    def _record(self, result: FetchResult) -> None:
        stamp = timeutil.compact(result.fetched_at, seconds=True)
        relative = Path("raw") / result.feed.value / f"{stamp}_{result.sha256[:12]}"
        relative = relative.with_suffix(_extension(result.content_type, result.url))
        target = self._case_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, result.content)
        self.records.append(
            ReplayRecord(
                feed=result.feed,
                url=result.url,
                fetched_at=result.fetched_at,
                sha256=result.sha256,
                path=relative.as_posix(),
                status_code=result.status_code,
                content_type=result.content_type,
            )
        )


def _charset(content_type: str | None) -> str:
    if content_type:
        for part in content_type.split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                return value.strip("\"'")
    return "utf-8"


def _retry_after_s(response: httpx.Response, default: float) -> float:
    value = response.headers.get("retry-after", "")
    try:
        seconds = float(value)
    except ValueError:
        seconds = default
    return min(max(seconds, 1.0), MAX_THROTTLE_WAIT_S)


def _extension(content_type: str | None, url: str) -> str:
    kind = (content_type or "").split(";")[0].strip().lower()
    known = {
        "application/json": ".json",
        "text/html": ".html",
        "text/plain": ".txt",
        "application/xml": ".xml",
        "text/xml": ".xml",
        "image/png": ".png",
        "image/jpeg": ".jpg",
    }
    if kind in known:
        return known[kind]
    path = urlsplit(url).path
    if path.endswith(".bz2"):
        return ".bz2"
    return ".bin"


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(data)
    temporary.replace(path)
