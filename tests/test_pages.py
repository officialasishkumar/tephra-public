"""The page routes and their redirects (SPEC-v2 2.1): Home at ``/``, the demo at ``/demo``, the
onboarding and workspace pages, ``/connect`` folded into onboarding, and the old Wall links that
land on the demo with their query kept byte for byte. Every page carries the page headers."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tephra.airline.sessions import COOKIE_NAME, AirlineClaims, sign_claims
from tephra.api.auth import wall_clock_now
from tephra.api.routes_pages import ONBOARD_PAGES, WEB_DIR, WORKSPACE_SECTIONS, without_hosted
from tephra.api.server import CONTENT_SECURITY_POLICY, create_app
from tephra.config import Settings
from tests.test_api import Harness

SECRET = "test-session-secret-0123456789abcdef"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin="zulu-4711",
        session_secret=SECRET,
        local_scheduler=False,
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings, runtime_factory=Harness().factory)
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


def _body(name: str) -> str:
    return (WEB_DIR / name).read_text(encoding="utf-8")


def _airline_cookie(settings: Settings) -> str:
    claims = AirlineClaims("AL-0123456789ab", "f" * 64, 1, "RFA", "Ring of Fire Air")
    token, _ = sign_claims(claims, settings, at=wall_clock_now())
    return token


PAGES = {
    "/": "home.html",
    "/demo": "index.html",
    "/assistant": "index.html",
    "/desk": "desk.html",
    "/guide": "guide.html",
    "/privacy": "privacy.html",
    "/docs/DOC-0123456789ab": "doc.html",
    "/onboard": "onboard.html",
    "/signin": "workspace.html",
    "/signin/recover": "workspace.html",
    "/workspace": "workspace.html",
    **{f"/onboard/{page}": "onboard.html" for page in sorted(ONBOARD_PAGES)},
    **{f"/workspace/{section}": "workspace.html" for section in sorted(WORKSPACE_SECTIONS)},
}


@pytest.mark.parametrize(("path", "page"), PAGES.items())
def test_each_page_serves_its_file_with_the_page_headers(
    client: TestClient, path: str, page: str
) -> None:
    response = client.get(path)
    assert response.status_code == 200, path
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    # with hosting off (this client) the privacy notice is served without its data-hosted parts
    expected = without_hosted(_body(page)) if path == "/privacy" else _body(page)
    assert response.text == expected
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["cache-control"] == "no-cache"


def test_the_onboarding_pages_and_workspace_sections_are_the_spec_s() -> None:
    assert {
        "airline",
        "policy",
        "fleet",
        "network",
        "schedule",
        "feeds",
        "people",
        "assistant",
        "review",
        "done",
    } == ONBOARD_PAGES
    assert {"answers", "feeds", "assistant"} == WORKSPACE_SECTIONS


@pytest.mark.parametrize(
    "path",
    [
        "/onboard/x",
        "/onboard/Airline",
        "/workspace/x",
        "/workspace/overview",
        "/workspace/kit",
        "/docs/x",
    ],
)
def test_an_unknown_page_is_not_found(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404, path
    assert response.json()["error"] == "not_found"


@pytest.mark.parametrize(
    "query",
    [
        "intro=0",
        "shots=1&present=1",
        "region=java_bali&x=%2Fa%20b",
        "a=1;b=2",
        "q=%E2%9C%93&empty=",
    ],
)
def test_an_old_wall_link_with_a_query_lands_on_the_demo_with_it(
    client: TestClient, query: str
) -> None:
    response = client.get(f"/?{query}")
    assert response.status_code == 307
    assert response.headers["location"] == f"/demo?{query}"
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


def test_home_without_a_query_is_home(client: TestClient) -> None:
    for path in ("/", "/?"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.text == _body("home.html")


def test_connect_lands_on_onboarding_signed_out_and_on_data_feeds_signed_in(
    client: TestClient, settings: Settings
) -> None:
    signed_out = client.get("/connect")
    assert signed_out.status_code == 307
    assert signed_out.headers["location"] == "/onboard"
    client.cookies.set(COOKIE_NAME, _airline_cookie(settings))
    signed_in = client.get("/connect")
    assert signed_in.status_code == 307
    assert signed_in.headers["location"] == "/workspace/feeds"
    client.cookies.set(COOKIE_NAME, "forged.cookie")
    assert client.get("/connect").headers["location"] == "/onboard"


def test_the_robots_file_disallows_everything(client: TestClient) -> None:
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.text == "User-agent: *\nDisallow: /\n"


def test_the_pages_are_not_in_the_api_schema(client: TestClient) -> None:
    paths = client.get("/api/openapi.json").json()["paths"]
    for path in ("/", "/demo", "/connect", "/onboard", "/onboard/{page}", "/workspace/{section}"):
        assert path not in paths, path


def test_the_pages_module_never_imports_the_server() -> None:
    source = (Path(__file__).resolve().parents[1] / "tephra/api/routes_pages.py").read_text()
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert imports
    for line in imports:
        assert "tephra.api.server" not in line, line
        assert not line.startswith("from tephra.api import") or "server" not in line, line
