"""The Desk's Airlines to verify and Data connections (SPEC-v2 §7.8): static checks of the
sources. The two menu items are a dispatcher's only (never a visitor's) and follow their
features; the Connect page is gone and its dispatcher tools call the same routes from a Desk
sheet; verifying says what it does not mean; nothing here names the old Wall address.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_the_menu_items_are_guarded_by_feature_and_role() -> None:
    account = _read("desk/account.js")
    assert "if (has('onboard') && !visitor) {" in account
    assert "'data-menu': 'airlines'" in account
    assert "text: 'Airlines to verify'" in account
    assert "if (has('connect') && !visitor) items.push(" in account
    assert "'data-menu': 'connections'" in account
    assert "text: 'Data connections'" in account
    assert "openAirlines();" in account
    assert "openConnections();" in account
    assert "href: '/connect'" not in account
    assert "Changes what the demo and every Desk show." in account


def test_the_connect_page_is_gone() -> None:
    for name in ("connect.html", "connect.js", "connect.css"):
        assert not (WEB / name).exists(), name
    html = _read("desk.html")
    assert 'href="/connect"' not in html
    assert '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>' in html
    assert '<a href="/demo">Demo</a>' in html
    assert '<html lang="en" data-theme="dark">' in html
    assert '<meta name="color-scheme" content="dark">' in html
    assert "See the demo, the public picture, with no sign-in" in html


def test_data_connections_call_the_push_tools_routes() -> None:
    conn = _read("desk/connections.js")
    for route in (
        "list: '/api/desk/connections'",
        "revoke: (id) => `/api/desk/connections/${encodeURIComponent(id)}/revoke`",
        "sample: '/api/desk/sample-feed'",
        "upload: '/api/desk/upload'",
    ):
        assert route in conn, route
    assert "api(PATH.list, { method: 'POST', body: { name: n } })" in conn
    assert "Shown once. Keep it with your push script." in conn
    assert "Stamp every record with TEPHRA's clock now" in conn
    assert "retime: S.retime" in conn


def test_the_airline_review_says_what_verifying_means() -> None:
    airlines = _read("desk/airlines.js")
    meaning = "It does not approve its policy or its use of TEPHRA, publishes nothing"
    assert f"{meaning} and changes no picture." in airlines
    assert "list: (status) => `/api/desk/airlines?status=${status}&limit=200`" in airlines
    assert "summary: '/api/desk/airlines/summary'" in airlines
    assert "act: (id, what) => `/api/desk/airlines/${encodeURIComponent(id)}/${what}`" in airlines
    for what in ("verify", "decline", "delete"):
        assert f"decide(a, '{what}'" in airlines
    assert "Someone changed this airline. Reloaded." in airlines
    assert "History does not check out" in airlines
    assert "Airlines are private to this site's dispatchers." in airlines
    assert "if (a.status === 'declined')" in airlines
    assert "Delete record…" in airlines


def test_crew_and_queue_name_the_new_pages() -> None:
    assert "(airline push)" in _read("desk/crew.js")
    assert "(Connect)" not in _read("desk/crew.js")
    queue = _read("desk/queue.js")
    assert "href: '/demo'" in queue
    assert "'See the demo'" in queue
    assert "See the Wall" not in queue
