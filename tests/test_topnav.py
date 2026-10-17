"""The shared nav (UI-DESIGN 7.25) without Assistant (owner, 16 Oct 2026): every page's nav is
Demo · Desk · Onboard · Guide, Onboard becoming Your airline once an airline is signed in. The
/assistant page stays, reached from the demo panel's pop-out link, the A key and the Guide."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
PAGES = (
    "home.html",
    "index.html",
    "desk.html",
    "guide.html",
    "doc.html",
    "privacy.html",
    "onboard.html",
    "workspace.html",
)


def _nav(page: str) -> str:
    html = (WEB / page).read_text(encoding="utf-8")
    navs = re.findall(r'<nav class="topnav" aria-label="TEPHRA pages">.*?</nav>', html)
    assert len(navs) == 1, page
    return navs[0]


@pytest.mark.parametrize("page", PAGES)
def test_the_nav_is_demo_desk_onboard_guide(page: str) -> None:
    nav = _nav(page)
    assert "/assistant" not in nav
    assert "Assistant" not in nav
    hrefs = re.findall(r'href="([^"]+)"', nav)
    assert hrefs == ["/demo", "/desk", "/onboard", "/guide"], page
    assert '<a href="/onboard" data-feature="onboard"' in nav


def test_no_script_adds_or_marks_an_assistant_link() -> None:
    for path in [*WEB.glob("*.js"), *WEB.glob("wall/*.js")]:
        source = path.read_text(encoding="utf-8")
        assert '.topnav a[href="/assistant"]' not in source, path.name


def test_signed_in_the_onboard_link_becomes_workspace_in_place() -> None:
    nav = (WEB / "account-nav.js").read_text(encoding="utf-8")
    swap = nav[nav.index("function swapNav() {") :]
    swap = swap[: swap.index("\n}\n")]
    assert '.topnav a[data-feature="onboard"]' in swap
    assert 'a.textContent = "Your airline";' in swap
    assert 'a.setAttribute("href", "/workspace");' in swap
    assert "assistant" not in swap.lower()


def test_the_assistant_page_is_still_reached_from_the_panel_and_the_guide() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")
    assert re.search(r'<a id="assist-page"[^>]*href="/assistant"', index)
    assert 'data-key="a" aria-keyshortcuts="A"' in index
    guide = (WEB / "guide.html").read_text(encoding="utf-8")
    body = guide[guide.index("</nav>") :]
    assert body.count('href="/assistant"') >= 2


def test_the_header_comment_names_the_nav_as_it_is() -> None:
    css = (WEB / "topnav.css").read_text(encoding="utf-8")
    assert "Demo · Desk · Onboard · Guide" in css
    assert "Demo · Assistant" not in css
