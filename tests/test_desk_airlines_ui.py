"""The Desk's Data connections (SPEC-v2 §7.8) and what the demo Desk is: static checks of the
sources. The demo Desk is RFA's dispatcher only (owner, 17 Oct 2026: "yes, do the split"):
Airlines to verify moved to TEPHRA staff's /admin, so the Desk has no such menu item, sheet or
module, and its sign-in says whose dispatcher you play. Data connections is a dispatcher's only
(never a visitor's) and follows its feature; the Connect page is gone and its dispatcher tools
call the same routes from a Desk sheet; nothing here names the old Wall address.
"""

from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_the_desk_has_no_airlines_to_verify() -> None:
    account = _read("desk/account.js")
    assert not (WEB / "desk" / "airlines.js").exists()
    for gone in ("'data-menu': 'airlines'", "Airlines to verify", "openAirlines", "airlines.js"):
        assert gone not in account, gone
    for page in ("desk.html", "desk.js", "desk.css"):
        assert "desk/airlines.js" not in _read(page), page
        assert "/api/desk/airlines" not in _read(page), page


def test_the_sign_in_says_whose_dispatcher_you_play() -> None:
    html = _read("desk.html")
    login = _read("desk/login.js")
    assert '<h1 id="login-title" class="login__title">RFA dispatcher · demo</h1>' in html
    words = "RFA is a fictional airline; you play its dispatcher on a replay."
    assert html.count(words) == 2  # the (i)'s words and its screen-reader copy
    assert "Dispatcher sign-in" not in html + login
    assert "Sign in to the Desk" not in html + login
    assert "on ${mode === 'LIVE' ? 'live public feeds' : 'a replay'}" in login


def test_data_connections_is_guarded_by_feature_and_role() -> None:
    account = _read("desk/account.js")
    assert "if (has('connect') && !visitor) items.push(" in account
    assert "'data-menu': 'connections'" in account
    assert "text: 'Data connections'" in account
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
    assert "Watch the demo, no sign-in" in html


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


def test_crew_and_queue_name_the_new_pages() -> None:
    assert "(airline push)" in _read("desk/crew.js")
    assert "(Connect)" not in _read("desk/crew.js")
    queue = _read("desk/queue.js")
    assert "href: '/demo'" in queue
    assert "'See the demo'" in queue
    assert "See the Wall" not in queue
