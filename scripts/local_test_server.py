"""Run TEPHRA locally with the fixed test values of docs/LOCAL-TEST-ACCOUNTS.md.

    uv run python scripts/local_test_server.py                 # hosting on,  http://127.0.0.1:8080
    uv run python scripts/local_test_server.py --hosting off   # hosting off, http://127.0.0.1:8081
    uv run python scripts/local_test_server.py --fresh         # delete this variant's data first

Every value is local-only and never works on the live site: the stub model (no model call can
be made), the Anak Krakatau replay, SQLite under ``.local-test/<on|off>/`` (gitignored), and the
Desk PIN, session secret and task token in ``ENV``. A ``.env`` file is not read,
GEMINI_API_KEY and GOOGLE_API_KEY are removed, and HTTP(S)_PROXY points at a dead local port, so
a stray outbound request fails at once.

With hosting on, a hosted airline's runtime is LIVE and would fetch real feeds and call Gemini
on the airline's key. Here, as in ``scripts/hosted_measure.py``:

- every hosted airline's model backend is the stub, whatever its key (a test key is fake);
- the airlines' feed source answers each URL from the recorded Anak Krakatau case
  (``httpx.MockTransport``), and airline-style callsigns in the recorded ADS-B become RFB or RFC;
- the process's wall clock reads the case clock (case start + time since this data directory
  first ran), so the recorded feeds look current; every hosted stamp is therefore case time.

The registry, the routes, the store and every check are the real code.
"""

import argparse
import os
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
DATA: Final = ROOT / ".local-test"
DEAD_PROXY: Final = "http://127.0.0.1:9"

ENV: Final[dict[str, str]] = {
    "TEPHRA_LLM": "stub",
    "TEPHRA_STORE": "sqlite",
    "TEPHRA_MODE": "REPLAY",
    "TEPHRA_REPLAY_CASE": "anak-krakatau-20260905",
    "TEPHRA_REPLAY_START": "2026-09-05T10:25:00Z",
    "TEPHRA_REPLAY_END": "2026-09-05T13:30:00Z",
    "TEPHRA_AUTO_REPLAY": "false",
    "TEPHRA_LOCAL_SCHEDULER": "true",
    "TEPHRA_DESK_PIN": "4242",
    "TEPHRA_SESSION_SECRET": "local-test-session-secret-not-for-live-0001",
    "TEPHRA_TASK_TOKEN": "local-test-task-token-not-for-live-0001",
    "TEPHRA_HOSTED_MAX_TENANTS": "3",
    "HTTP_PROXY": DEAD_PROXY,
    "HTTPS_PROXY": DEAD_PROXY,
    "ALL_PROXY": DEAD_PROXY,
    "NO_PROXY": "127.0.0.1,localhost",
}
FEATURES: Final = {"on": "connect,onboard,hosted", "off": "connect,onboard"}
PORTS: Final = {"on": 8080, "off": 8081}
REMOVED: Final = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "TEPHRA_KEY_SECRET")


def seeded_file(port: int) -> Path:
    """Where ``scripts/local_test_seed.py`` keeps the values the server made at random."""
    return DATA / f"seeded-{port}.txt"


def environment(hosting: str, port: int, data: Path) -> dict[str, str]:
    """The fixed values, this variant's features, port and data directory."""
    return {
        **ENV,
        "TEPHRA_FEATURES": FEATURES[hosting],
        "TEPHRA_PORT": str(port),
        "TEPHRA_SQLITE_PATH": str(data / "tephra.sqlite3"),
        "TEPHRA_CACHE_DIR": str(data / "cache"),
    }


def case_t0(data: Path) -> float:
    """When this data directory first ran: a restart keeps the case clock going."""
    marker = data / "case-clock-t0"
    if marker.exists():
        return float(marker.read_text(encoding="utf-8"))
    t0 = time.time()
    marker.write_text(f"{t0}\n", encoding="utf-8")
    return t0


def offline_hosting(t0: float) -> Any:
    """The hosted harness above; returns the registry factory ``create_app`` takes."""
    import httpx

    from tephra.agents import llm as llm_module
    from tephra.config import PROJECT_ROOT
    from tephra.feeds.base import HttpSource, SharedHttpSource
    from tephra.hosted.registry import TenantRegistry
    from tephra.pipeline import create_runtime
    from tephra.replay.cases import ReplaySource, case_path, select_case
    from tephra.util import timeutil

    sys.path.insert(0, str(ROOT / "scripts"))
    from hosted_measure import ADSB_HOST, CASE, START, RecordedTransport

    class CaseClock:
        def now(self) -> datetime:
            return datetime.fromtimestamp(START.timestamp() + (time.time() - t0), UTC)

    clock = CaseClock()
    timeutil.SystemClock.now = lambda self: clock.now()  # type: ignore[method-assign]

    real_get_llm = llm_module.get_llm

    def stub_for_airlines(settings: Any, *, quota: Any = None) -> Any:
        if settings.hosted_tenant is not None:
            return llm_module.StubBackend()
        return real_get_llm(settings, quota=quota)

    llm_module.get_llm = stub_for_airlines

    async def factory(settings: Any, **kw: Any) -> Any:
        runtime = await create_runtime(settings, **kw)
        if kw.get("hosted") is not None:
            runtime.wall_clock = clock
        return runtime

    def registry(settings: Any, root: Any, demo: Any, meter: Any, access: Any) -> Any:
        case = select_case(PROJECT_ROOT / "data", CASE)
        recorded = RecordedTransport(ReplaySource(case_path(PROJECT_ROOT / "data", CASE), case))
        inner = HttpSource(
            cache_dir=Path(settings.cache_dir) / "local-test-http",
            retries=0,
            host_intervals_s={ADSB_HOST: 0.0},
            transport=httpx.MockTransport(recorded.handle),
            clock=clock,
        )
        source = SharedHttpSource(inner, settings=settings, clock=lambda: clock.now().timestamp())
        return TenantRegistry(settings, root, demo, meter, access, factory=factory, source=source)

    return registry


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hosting", choices=("on", "off"), default="on")
    parser.add_argument("--port", type=int, help="default 8080 (hosting on) or 8081 (off)")
    parser.add_argument("--fresh", action="store_true", help="delete this variant's data first")
    args = parser.parse_args()

    data = DATA / args.hosting
    port = args.port or PORTS[args.hosting]
    if args.fresh:
        shutil.rmtree(data, ignore_errors=True)
        seeded_file(port).unlink(missing_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    for name in REMOVED:
        os.environ.pop(name, None)
    os.environ.update(environment(args.hosting, port, data))

    import uvicorn

    from tephra.api.server import configure_logging, create_app
    from tephra.config import Settings, apply_process_env

    settings = Settings(_env_file=None)  # these values only: a .env file is not read
    if settings.llm != "stub" or settings.gemini_api_key is not None:
        sys.exit("local_test_server: runs only the stub model, with no GEMINI_API_KEY")
    apply_process_env(settings)
    configure_logging(settings.log_level, project=None)
    registry = offline_hosting(case_t0(data)) if args.hosting == "on" else None
    app = create_app(settings, registry_factory=registry)
    print(f"local test server (hosting {args.hosting}): http://127.0.0.1:{port}", flush=True)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        log_level="info",
        access_log=False,
        timeout_graceful_shutdown=8,
    )


if __name__ == "__main__":
    main()
