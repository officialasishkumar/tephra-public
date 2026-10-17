"""The hosted pages: an airline's shells under /a/<ICAO>/, the join page and the operators'
console. The shell is the same for every ICAO (membership is the API's answer), each hosted
page says noindex, a reader without an airline cookie is sent to sign in and back, and no
page route carries a token (invite tokens travel in the URL fragment)."""

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from tephra.airline.sessions import COOKIE_NAME as AIRLINE_COOKIE
from tephra.api.routes_pages import WEB_DIR
from tests.test_tenancy_routes import FakeHosted, airline_cookie, hosted_settings

SHELLS = {
    "/a/RFB/": "index.html",
    "/a/RFB/desk": "desk.html",
    "/a/RFB/feeds": "hosted.html",
    "/a/RFB/settings": "hosted.html",
    "/a/RFB/settings/policy": "hosted.html",
    "/a/RFB/settings/assistant": "hosted.html",
    "/a/RFB/settings/people": "hosted.html",
    "/a/RFB/settings/record": "hosted.html",
    "/a/RFB/docs/DOC-0123456789ab": "doc.html",
    "/a/RFB/docs/ho_0123456789ab": "doc.html",
}


@pytest.fixture
def hosted(tmp_path: Path) -> FakeHosted:
    return FakeHosted(hosted_settings(tmp_path))


@pytest.fixture
def client(hosted: FakeHosted) -> Iterator[TestClient]:
    with TestClient(hosted.app(), follow_redirects=False) as test_client:
        yield test_client


def signed_in(client: TestClient, hosted: FakeHosted) -> None:
    client.cookies.set(AIRLINE_COOKIE, airline_cookie(hosted.settings))


def shell_present(name: str) -> bool:
    return (WEB_DIR / name).is_file()


@pytest.mark.parametrize(("path", "shell"), sorted(SHELLS.items()))
def test_each_airline_page_is_the_site_s_own_shell(
    client: TestClient, hosted: FakeHosted, path: str, shell: str
) -> None:
    signed_in(client, hosted)
    response = client.get(path)
    if not shell_present(shell):
        pytest.skip(f"{shell} is not installed in this tree yet")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["x-robots-tag"] == "noindex"
    assert response.content == (WEB_DIR / shell).read_bytes()
    assert "content-security-policy" in response.headers


def test_the_shell_is_the_same_for_any_airline_code(client: TestClient, hosted: FakeHosted) -> None:
    signed_in(client, hosted)
    pages = [client.get(f"/a/{icao}/desk") for icao in ("RFB", "RFC", "ZZZ")]
    assert {page.status_code for page in pages} == {200}
    assert len({page.content for page in pages}) == 1


@pytest.mark.parametrize("path", sorted(SHELLS))
def test_a_reader_without_a_cookie_is_sent_to_sign_in_and_back(
    client: TestClient, path: str
) -> None:
    response = client.get(path)
    assert response.status_code == 303
    assert response.headers["location"] == f"/signin?next={path}"
    assert response.headers["x-robots-tag"] == "noindex"


def test_a_forged_or_expired_cookie_counts_as_none(client: TestClient) -> None:
    client.cookies.set(AIRLINE_COOKIE, "e30.AAAA")
    assert client.get("/a/RFB/desk").status_code == 303


def test_the_bare_airline_path_gains_its_slash(client: TestClient, hosted: FakeHosted) -> None:
    assert client.get("/a/RFB").headers["location"] == "/signin?next=/a/RFB"
    signed_in(client, hosted)
    response = client.get("/a/RFB")
    assert response.status_code == 308
    assert response.headers["location"] == "/a/RFB/"


@pytest.mark.parametrize(
    "path",
    [
        "/a/RFB/settings/billing",
        "/a/RFB/docs/not-a-doc",
        "/a/RFB/workspace",
        "/a/rfb/desk",
        "/a/RFBX/desk",
        "/a/R1B/desk",
    ],
)
def test_unknown_airline_pages_are_404(client: TestClient, hosted: FakeHosted, path: str) -> None:
    signed_in(client, hosted)
    assert client.get(path).status_code == 404


@pytest.mark.parametrize(("path", "shell"), [("/join", "workspace.html"), ("/admin", "admin.html")])
def test_join_and_the_console_need_no_cookie_and_say_noindex(
    client: TestClient, path: str, shell: str
) -> None:
    if not shell_present(shell):
        pytest.skip(f"{shell} is not installed in this tree yet")
    for target in (path, f"{path}/join" if path == "/admin" else path):
        response = client.get(target)
        assert response.status_code == 200
        assert response.headers["x-robots-tag"] == "noindex"
        assert response.content == (WEB_DIR / shell).read_bytes()


def test_the_demo_pages_stay_indexable_as_today(client: TestClient) -> None:
    for path in ("/", "/demo", "/desk", "/workspace"):
        assert "x-robots-tag" not in client.get(path).headers


def test_no_page_or_api_route_carries_a_token(client: TestClient) -> None:
    app = cast(FastAPI, client.app)
    paths = [
        str(context.path_format)
        for context in iter_route_contexts(app.routes)
        if isinstance(context.original_route, APIRoute)
    ]
    assert any(path.startswith("/a/") for path in paths)
    assert [path for path in paths if "token" in path.lower()] == []
    # an invite link's token never reaches the server: /join#<token>, /admin/join#<token>
    assert "/join" in paths
    assert "/admin/join" in paths
