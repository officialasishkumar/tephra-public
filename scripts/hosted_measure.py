"""Measure two hosted LIVE airline runtimes offline: memory, CPU per tick, store operations.

SPEC-FINAL §7 and F16 ask for LIVE numbers before more than one airline is hosted. This plays a
recorded replay case to two hosted runtimes as if it were live: both fetch through one
``SharedHttpSource`` whose ``HttpSource`` has an ``httpx.MockTransport`` answering each URL with
the case's recorded response (the latest at or before the case clock), and both runtimes are
bound to that clock, so the feeds look current. Nothing leaves the machine: no network, no
Gemini (the stub model), SQLite under a scratch directory.

The recording is real traffic, and the hosted airlines are the fictional Ring of Fire Charter
(RFB) and Ring of Fire Cargo (RFC): every airline-style callsign in the recorded ADS-B is given
one of the two designators (by a stable hash of its own), so each airline's own fleet is about
half of the traffic, flying the recorded tracks.

Each step is one tick (the clock moves 60 s), one ADS-B pass 30 s later, and the AI worker's
queued work, for both runtimes; each step empties the airline caches first and runs with
them on, as the registry's hosted pass does (D19). Reported: the process's peak RSS before the
runtimes, after they are made and after the run; CPU seconds per step per airline; and store
operations per step by kind and airline, counted as Firestore bills them (``StoreMeter``).

    uv run python scripts/hosted_measure.py --ticks 120
"""

import argparse
import asyncio
import json
import resource
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from tephra.config import HOSTED_FEATURES, PROJECT_ROOT, Settings
from tephra.feeds.airports import load_airports
from tephra.feeds.base import FetchError, HttpSource, SharedHttpSource
from tephra.feeds.routes import load_routes
from tephra.feeds.volcanoes import load_volcanoes
from tephra.models import FeedId
from tephra.pipeline import HostedParts, Runtime, create_runtime
from tephra.policy import load_policy
from tephra.replay.cases import ReplaySource, case_path, select_case
from tephra.scheduler import run_adsb_pass
from tephra.store.metered import TENANT_CACHED, MeteredStore, StoreMeter
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.hashing import sha256_text

CASE = "anak-krakatau-20260905"
START = datetime(2026, 9, 5, 10, 25, tzinfo=UTC)
AIRLINES: dict[str, tuple[str, str | None]] = {
    "RFB": ("Ring of Fire Charter", "RB"),
    "RFC": ("Ring of Fire Cargo", None),
}
ADSB_HOST = "api.adsb.lol"


class CaseClock:
    """The case time both runtimes are bound to; the script moves it."""

    def __init__(self, at: datetime) -> None:
        self.at = at

    def now(self) -> datetime:
        return self.at


class RecordedTransport:
    """Answers each request with the case's recorded response for its URL, at the case clock;
    airline callsigns in ADS-B answers get RFB or RFC as their designator."""

    def __init__(self, replay: ReplaySource) -> None:
        self._replay = replay
        self.served = 0
        self.missing: set[str] = set()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        try:
            result = await self._replay.fetch(url, feed=FeedId.SIGMET)
        except FetchError:
            self.missing.add(url.split("?")[0])
            return httpx.Response(404)
        self.served += 1
        content = result.content
        if request.url.host == ADSB_HOST and result.status_code == 200:
            content = _fictional_callsigns(content)
        headers = {"content-type": result.content_type or "application/octet-stream"}
        return httpx.Response(result.status_code, content=content, headers=headers)


def _fictional_callsigns(content: bytes) -> bytes:
    body = json.loads(content)
    for aircraft in body.get("ac") or []:
        flight = (aircraft.get("flight") or "").strip()
        if len(flight) > 3 and flight[:3].isalpha() and flight[3:].isdigit():
            designator = "RFB" if int(sha256_text(flight[:3])[:2], 16) % 2 == 0 else "RFC"
            aircraft["flight"] = f"{designator}{flight[3:]:<5}"
    return json.dumps(body).encode()


def airline_settings(root: Path, icao: str) -> Settings:
    name, iata = AIRLINES[icao]
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=root / "tenants" / f"{icao}.sqlite3",
        cache_dir=root / "cache",
        features=HOSTED_FEATURES,
        recovery_auto=False,
        science=False,
        visitor_access="off",
        fleet_prefixes=icao,
        airline_name=name,
        airline_icao=icao,
        airline_iata=iata,
        hosted_tenant=icao,
        hosted_stage="live",
        tick_deadline_s=25,
        local_scheduler=False,
    )


def peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024, 1)


async def make_airline(
    root: Path, icao: str, meter: StoreMeter, source: SharedHttpSource, clock: CaseClock
) -> Runtime:
    settings = airline_settings(root, icao)
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    policy = load_policy(settings.data_dir, settings.policy_file)
    parts = HostedParts(
        tenant=icao,
        store=MeteredStore(
            SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs"),
            meter,
            icao,
            cache=TENANT_CACHED,
        ),
        source=source,
        catalogue=load_volcanoes(settings.data_dir),
        airports=load_airports(
            settings.data_dir, min_runway_m=policy.alternates.min_runway_m.value
        ),
        routes=load_routes(settings.data_dir),
        policy=policy,
        own_schedule=None,
        llm_unavailable=None,
        fence=lambda: False,
    )
    runtime = await create_runtime(settings, hosted=parts)
    runtime.wall_clock = clock
    return runtime


async def step(runtime: Runtime, clock: CaseClock, at: datetime) -> dict[str, Any]:
    """One tick at ``at``, the ADS-B pass 30 s later and the work they made due."""
    started = time.process_time()
    store = runtime.store
    if isinstance(store, MeteredStore):  # as the registry's pass: cache on, emptied each pass
        store.enable_cache()
        store.clear_cache()
    clock.at = at
    report = await runtime.tick(reason="manual")
    with runtime.bound():
        work = [await runtime.worker.drain()]
        clock.at = at + timedelta(seconds=30)
        await run_adsb_pass(runtime)
        work.append(await runtime.worker.drain())
    return {
        "cpu_s": time.process_time() - started,
        "exposed": report.exposed_flights,
        "drafts": sum(done.drafts_created for done in work),
    }


async def measure(ticks: int, root: Path) -> dict[str, Any]:
    case = select_case(PROJECT_ROOT / "data", CASE)
    transport = RecordedTransport(ReplaySource(case_path(PROJECT_ROOT / "data", CASE), case))
    clock = CaseClock(START)
    inner = HttpSource(
        cache_dir=root / "cache",
        retries=0,
        host_intervals_s={ADSB_HOST: 0.0},
        transport=httpx.MockTransport(transport.handle),
        clock=clock,
    )
    source = SharedHttpSource(inner, clock=lambda: clock.at.timestamp())
    meter = StoreMeter(blob_puts_cap=4_000, clock=clock)
    rss_before = peak_rss_mb()
    airlines = {icao: await make_airline(root, icao, meter, source, clock) for icao in AIRLINES}
    rss_made = peak_rss_mb()
    rows: dict[str, list[dict[str, Any]]] = {icao: [] for icao in airlines}
    try:
        for n in range(ticks):
            at = START + timedelta(minutes=n)
            for icao, runtime in airlines.items():
                rows[icao].append(await step(runtime, clock, at))
    finally:
        for runtime in airlines.values():
            await runtime.aclose()
            await runtime.store.aclose()
        await inner.aclose()
    day = meter.day()
    per_airline: dict[str, Any] = {}
    for icao, steps in rows.items():
        cpu = [row["cpu_s"] for row in steps]
        per_airline[icao] = {
            "cpu_s_per_step_mean": round(sum(cpu) / len(cpu), 4),
            "cpu_s_per_step_max": round(max(cpu), 4),
            "exposed_max": max(row["exposed"] for row in steps),
            "drafts": sum(row["drafts"] for row in steps),
            "per_step": {
                kind: round(getattr(day, kind).get(icao, 0) / len(steps), 1)
                for kind in ("reads", "writes", "deletes")
            },
            "totals": {
                kind: getattr(day, kind).get(icao, 0) for kind in ("reads", "writes", "deletes")
            },
        }
    return {
        "case": CASE,
        "from": timeutil.to_iso(START),
        "steps": ticks,
        "step": "tick + ADS-B pass 30 s later + AI worker (stub), per airline",
        "peak_rss_mb": {
            "before": rss_before,
            "two_airlines_made": rss_made,
            "after": peak_rss_mb(),
        },
        "airlines": per_airline,
        "blob_puts": day.blob_puts,
        "recorded_responses_served": transport.served,
        "urls_not_recorded": sorted(transport.missing),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ticks", type=int, default=120, help="steps to run (default 120)")
    parser.add_argument("--out-dir", type=Path, help="scratch directory (default: a new temp)")
    args = parser.parse_args()
    root = args.out_dir or Path(tempfile.mkdtemp(prefix="tephra-hosted-measure-"))
    result = asyncio.run(measure(args.ticks, root))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
