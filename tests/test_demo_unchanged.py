"""With ``hosted`` off the site answers byte for byte as it did before hosting existed (the
commit bc3fac9), and with ``hosted`` on the demo's own answers do not change.

``capture`` replays a fixed list of requests against the app with the stand-in runtime of
tests/test_api.py on a fixed clock, and hashes each answer's status, the headers a browser acts
on, and the body. ``PINNED`` holds the same hashes computed by running ``capture`` against a
``git archive bc3fac9`` copy of ``tephra/``, ``tests/`` and ``data/`` (the tree before hosting):
nothing it uses is newer than that commit. ``/api/openapi.json`` is left out: it grows by the
new enum values (SPEC §0 rule 8).
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tephra.api.auth import COOKIE_NAME, sign_session, wall_clock_now
from tephra.api.server import create_app
from tephra.config import Settings
from tephra.util import timeutil
from tests.test_api import Harness
from tests.test_tenancy_routes import FakeHosted

AT = datetime(2026, 10, 17, 6, 0, tzinfo=UTC)
PIN = "zulu-4711"
TASK_TOKEN = "task-token-for-tests-0123456789abcdef"
SECRET = "test-session-secret-0123456789abcdef"
HEADERS = (
    "content-type",
    "cache-control",
    "content-security-policy",
    "x-content-type-options",
    "referrer-policy",
    "x-frame-options",
    "permissions-policy",
    "etag",
    "content-disposition",
    "allow",
    "retry-after",
    "location",
    "x-robots-tag",
)
JSON = {"Content-Type": "application/json"}

REQUESTS: tuple[tuple[str, str, dict[str, Any] | None, bool], ...] = (
    # (method, path, JSON body, with a Desk session)
    ("GET", "/", None, False),
    ("GET", "/demo", None, False),
    ("GET", "/desk", None, False),
    ("GET", "/assistant", None, False),
    ("GET", "/guide", None, False),
    ("GET", "/privacy", None, False),
    ("GET", "/robots.txt", None, False),
    ("GET", "/docs/DOC-0123456789ab", None, False),
    ("GET", "/onboard", None, False),
    ("GET", "/workspace", None, False),
    ("GET", "/signin", None, False),
    ("GET", "/health", None, False),
    ("GET", "/api/state", None, False),
    ("GET", "/api/wall", None, False),
    ("GET", "/api/advisories", None, False),
    ("GET", "/api/advisories?status=DRAFT&limit=5", None, False),
    ("GET", "/api/audit", None, False),
    ("GET", "/api/audit/verify", None, False),
    ("GET", "/api/outbound", None, False),
    ("GET", "/api/feeds", None, False),
    ("GET", "/api/policy", None, False),
    ("GET", "/api/replays", None, False),
    ("GET", "/api/airports", None, False),
    ("GET", "/api/routes/WIII/WADD", None, False),
    ("GET", "/api/blobs/nothing", None, False),
    ("GET", "/api/connect/format", None, False),
    ("GET", "/api/connect/schema.json", None, False),
    ("GET", "/api/airline/session", None, False),
    ("GET", "/api/desk/me", None, False),
    ("GET", "/api/desk/advisories", None, False),
    ("GET", "/api/desk/advisories", None, True),
    ("GET", "/api/desk/ai-failures", None, True),
    ("GET", "/api/duty", None, False),
    ("GET", "/api/advisories/adv_0123456789ab/chain", None, False),
    ("GET", "/api/mode", None, False),
    ("POST", "/api/desk/login", {}, False),
    ("POST", "/api/push/positions", {"format": "tephra.positions/1", "positions": [{}]}, False),
    ("POST", "/tasks/tick", None, False),
    ("GET", "/api/nothing-here", None, False),
    ("GET", "/a/RFB/", None, False),
    ("GET", "/a/RFB/api/state", None, False),
    ("GET", "/join", None, False),
    ("GET", "/admin", None, False),
    ("GET", "/api/hosted/me", None, False),
    ("GET", "/api/tenant/header", None, False),
    ("GET", "/api/admin/me", None, False),
)


def capture_settings(root: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "llm": "stub",
        "store": "sqlite",
        "sqlite_path": root / "tephra.sqlite3",
        "cache_dir": root / "cache",
        "data_dir": root / "data",
        "desk_pin": PIN,
        "task_token": TASK_TOKEN,
        "session_secret": SECRET,
        "local_scheduler": False,
        "features": "connect,crew,notices,onboard",
    }
    return Settings(_env_file=None, **{**values, **overrides})


def answer_hash(status: int, headers: Any, body: bytes) -> str:
    """An HTML page counts by its status and headers only: its file is the web packages' to
    change (their tests cover it); what the server answers around it must not change."""
    page = headers.get("content-type", "").startswith("text/html")
    digest = hashlib.sha256(str(status).encode())
    for name in HEADERS:
        if not (page and name == "etag"):  # a file's ETag follows its mtime and size
            digest.update(f"\n{name}:{headers.get(name, '')}".encode())
    if not page:
        digest.update(b"\n\n" + body)
    return digest.hexdigest()[:32]


def capture(settings: Settings, **app_options: Any) -> dict[str, str]:
    """``"METHOD path[ +session]" -> hash`` for every request of :data:`REQUESTS`."""
    found: dict[str, str] = {}
    with (
        timeutil.use_clock(timeutil.FixedClock(AT)),
        TestClient(create_app(settings, **app_options), raise_server_exceptions=False) as client,
    ):
        token, _ = sign_session("Ana K", settings, at=wall_clock_now(), sid="0011223344556677")
        for method, path, body, signed_in in REQUESTS:
            client.cookies.clear()
            if signed_in:
                client.cookies.set(COOKIE_NAME, token)
            response = client.request(
                method, path, json=body, headers=JSON if body is not None else None
            )
            label = f"{method} {path}{' +session' if signed_in else ''}"
            found[label] = answer_hash(response.status_code, response.headers, response.content)
    return found


PINNED: dict[str, str] = {
    "GET /": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /a/RFB/": "f04ec4932e103b7a554820aeba9c2ff8",
    "GET /a/RFB/api/state": "f04ec4932e103b7a554820aeba9c2ff8",
    "GET /admin": "f04ec4932e103b7a554820aeba9c2ff8",
    "GET /api/admin/me": "1a6aa327bd771201dec3b1108de36f93",
    "GET /api/advisories": "30c25316160ccc8056ad77bf7c9e65aa",
    "GET /api/advisories/adv_0123456789ab/chain": "750f7d23c1be20acb2f0903f43f92e9b",
    "GET /api/advisories?status=DRAFT&limit=5": "30c25316160ccc8056ad77bf7c9e65aa",
    "GET /api/airline/session": "dbc0b0bbc6c546a73fb9607a5ff1d877",
    "GET /api/airports": "2d768f1a78bb98f49485e06d15e84a1b",
    "GET /api/audit": "66d7718bee99bec8c65624243128fbfa",
    "GET /api/audit/verify": "b60ea951cd3892103a531b997c273c75",
    "GET /api/blobs/nothing": "b91993aff7c74aa1346f0cd9a50960e5",
    "GET /api/connect/format": "aa5525c36dc5bfa737d61c60d3c89c8f",
    "GET /api/connect/schema.json": "54157cd95a41988142d74e8b9b5fac93",
    "GET /api/desk/advisories": "165aa66f3a09985fffec422a3c768775",
    "GET /api/desk/advisories +session": "30c25316160ccc8056ad77bf7c9e65aa",
    "GET /api/desk/ai-failures +session": "45ddbe333d063f79af5fb3a1885e43fc",
    "GET /api/desk/me": "165aa66f3a09985fffec422a3c768775",
    "GET /api/duty": "8ce6f41327152e495c5c994566d7756c",
    "GET /api/feeds": "3a1932ce30b442feba6b2c9bb7e05e3f",
    "GET /api/hosted/me": "1a6aa327bd771201dec3b1108de36f93",
    "GET /api/mode": "5b4d6a8c4c1e3f7bae771956df0dc1e3",
    "GET /api/nothing-here": "1a6aa327bd771201dec3b1108de36f93",
    "GET /api/outbound": "9397ebfb71313bf67e65e2ea94104de4",
    "GET /api/policy": "2f14c19e0c76f76c4aa73cbf6f6f03f9",
    "GET /api/replays": "02766350361206c278abc0b1c38bf6cb",
    "GET /api/routes/WIII/WADD": "b60ea951cd3892103a531b997c273c75",
    "GET /api/state": "ea297bf8907c8899939aafe1221d4d71",
    "GET /api/tenant/header": "1a6aa327bd771201dec3b1108de36f93",
    "GET /api/wall": "0fd2a2e4674ab9aa30660ad7bbece8e2",
    "GET /assistant": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /demo": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /desk": "8e065602941f94037279568d7365b061",
    "GET /docs/DOC-0123456789ab": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /guide": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /health": "5b7bf200ec4ed3d69fe514d899b9fbf3",
    "GET /join": "f04ec4932e103b7a554820aeba9c2ff8",
    "GET /onboard": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /privacy": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /robots.txt": "5c6712ee4f577e8f99bab07f19b32f3c",
    "GET /signin": "3a1fecc86128301962ebaaff1eb9f49d",
    "GET /workspace": "3a1fecc86128301962ebaaff1eb9f49d",
    "POST /api/desk/login": "eaeadfd0b1c7cfc8ca31b66d5e098c3b",
    "POST /api/push/positions": "9bc90b554d3037ce2d0e5cdd6fa52a19",
    "POST /tasks/tick": "ac30aab07692a0044ecdf553e3a3a6aa",
}
"""Computed from bc3fac9 (the module docstring says how)."""


@pytest.fixture
def base(tmp_path: Path) -> Settings:
    return capture_settings(tmp_path)


def test_with_hosted_off_every_answer_is_the_one_bc3fac9_gave(base: Settings) -> None:
    now = capture(base, runtime_factory=Harness().factory)
    assert set(now) == set(PINNED)
    changed = sorted(label for label in PINNED if now[label] != PINNED[label])
    assert changed == []


HOSTED_ONLY: tuple[str, ...] = (
    "/a/",
    "/join",
    "/admin",
    "/api/hosted/",
    "/api/tenant/",
    "/api/admin/",
)


def test_with_hosted_on_and_two_airlines_the_demo_answers_as_with_it_off(
    base: Settings, tmp_path: Path
) -> None:
    off = capture(base, runtime_factory=Harness().factory)
    on_settings = capture_settings(tmp_path / "on", features="connect,crew,notices,onboard,hosted")
    hosted = FakeHosted(on_settings)
    assert set(hosted.registry.handles) == {"RFB", "RFC"}
    on = capture(
        on_settings,
        runtime_factory=hosted.runtime_factory,
        registry_factory=hosted.registry_factory,
    )
    demo = [label for label in off if not label.split(" ")[1].startswith(HOSTED_ONLY)]
    assert len(demo) > 35
    assert [label for label in demo if on[label] != off[label]] == []
