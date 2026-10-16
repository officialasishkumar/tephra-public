"""The demo's layout (SPEC v2 3.5, 5.2): a static check of ``index.html``, ``wall.js``,
``wall.css`` and ``page-mode.js``.

The slim story strip is folded by default, the side panel holds TEPHRA Assistant and Details as
two ARIA tabs over the demo's one filled button, the welcome dialog opens from wall.js unless a
query or a deep link says not to, the old Wall's second right panels are gone, the map keeps the
night palette in both themes and /assistant stays dark.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
WALL = (WEB / "wall.js").read_text(encoding="utf-8")
CSS = (WEB / "wall.css").read_text(encoding="utf-8")
STORY = (WEB / "wall" / "story.js").read_text(encoding="utf-8")

# SPEC v2 3.5. `story-strip` is not here: the strip under the old drawer repeated the story strip
# beside it, and its "Story" button closed a drawer that no longer exists.
IDS = [
    "how-btn",
    "welcome",
    "rail",
    "rail-btn",
    "rail-vol",
    "rail-region",
    "rail-code",
    "rail-scope",
    "rail-exposed",
    "rail-active",
    "rail-drafts",
    "rail-at",
    "story",
    "story-fold",
    "side",
    "side-tabs",
    "assist-tab",
    "details-btn",
    "assist-page",
    "assist",
    "ai-state",
    "model-chip",
    "assist-player",
    "assist-pipe",
    "assist-now",
    "assist-log",
    "assist-live",
    "details",
    "details-title",
    "details-back",
    "details-fold",
    "details-volcano",
    "details-body",
    "xtabs",
    "brief",
    "xpanel",
    "flights",
    "decisions",
    "trace",
    "levels",
    "layers-pop",
    "feeds",
    "history",
    "crew",
    "side-foot",
    "side-desk",
    "side-handle",
]
GONE = ["ai-chip", "details-sheet", "cta-sticky", "panel-toggle", "phone-bar", "story-strip"]


def _tag(ident: str) -> str:
    m = re.search(rf'<[a-z]+[^>]*\bid="{re.escape(ident)}"[^>]*>', INDEX)
    assert m, ident
    return m.group(0)


@pytest.mark.parametrize("ident", IDS)
def test_every_demo_id_is_in_the_page(ident: str) -> None:
    assert _tag(ident)


@pytest.mark.parametrize("ident", GONE)
def test_the_old_second_panels_are_gone(ident: str) -> None:
    assert f'id="{ident}"' not in INDEX
    assert f'"{ident}"' not in WALL


def test_the_nav_is_the_shared_one_with_demo_current() -> None:
    nav = (
        '<nav class="topnav" aria-label="TEPHRA pages"><a href="/demo" aria-current="page">Demo</a>'
        '<a href="/assistant">Assistant</a><a class="topnav__keep" href="/desk">Desk</a>'
        '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>'
        '<a href="/guide">Guide</a></nav>'
    )
    assert nav in INDEX
    assert 'href="/connect"' not in INDEX
    assert '.topnav a[href="/demo"]' in WALL
    assert '.topnav a[href="/"]' not in WALL


def test_the_head_loads_the_theme_first_and_both_schemes() -> None:
    assert '<meta name="color-scheme" content="dark light">' in INDEX
    assert (
        INDEX.index("/static/theme-boot.js")
        < INDEX.index("/static/page-mode.js")
        < INDEX.index("wall.css")
    )
    for sheet in ("/static/welcome.css", "/static/five-steps.css"):
        assert f'<link rel="stylesheet" href="{sheet}">' in INDEX
    # no inline script or style (the CSP has no 'unsafe-inline')
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", INDEX)
    assert " style=" not in INDEX
    assert "<style" not in INDEX


def test_the_side_panel_is_two_tabs_with_assistant_selected() -> None:
    tabs = INDEX[INDEX.index('id="side-tabs"') : INDEX.index('id="assist" ')]
    assert 'role="tablist"' in _tag("side-tabs")
    assert tabs.count('role="tab"') == 2
    assist = _tag("assist-tab")
    assert 'aria-selected="true"' in assist
    assert 'aria-controls="assist"' in assist
    details = _tag("details-btn")
    assert 'aria-selected="false"' in details
    assert 'tabindex="-1"' in details
    assert 'aria-controls="details"' in details
    assert 'role="tabpanel"' in _tag("assist")
    assert 'aria-labelledby="assist-tab"' in _tag("assist")
    assert 'role="tabpanel"' in _tag("details")
    assert "hidden" in _tag("details")
    # roving tabindex, arrows and Home/End (wall.js)
    assert "ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1" in WALL
    assert "Open TEPHRA Assistant as a page" in INDEX


def test_the_demo_has_one_filled_button_and_it_opens_the_desk() -> None:
    assert INDEX.count("btn--primary") == 1
    desk = _tag("side-desk")
    assert 'class="btn btn--primary"' in desk
    assert 'href="/desk"' in desk
    foot = INDEX[
        INDEX.index('id="side-foot"') : INDEX.index("</aside>", INDEX.index('id="side-foot"'))
    ]
    assert "You decide" in foot
    assert (
        "Drafts wait at the Desk for a dispatcher. Nothing leaves TEPHRA until one approves."
        in foot
    )
    # the story's call to action is drawn outlined (the logic and its tests stay)
    cta = CSS[CSS.index("\n.cta {") : CSS.index(".cta:hover")]
    assert "border: 1px solid var(--c-line-input)" in cta
    assert "--c-cta" not in cta


def test_the_story_is_folded_to_its_strip_by_default() -> None:
    assert "hidden" in _tag("story")
    rail = _tag("rail-btn")
    assert 'aria-expanded="false"' in rail
    assert 'aria-controls="story"' in rail
    assert 'aria-keyshortcuts="E"' in rail
    fold = _tag("story-fold")
    assert 'aria-expanded="true"' in fold
    assert "‹ Fold the story" in INDEX  # noqa: RUF001  the UI's own chevron
    assert 'const STORY_KEY = "tephra.demo.story";' in WALL
    assert 'storyOpen: !PRESENT && !SHOTS && session(STORY_KEY) === "open"' in WALL
    assert '(open ? $("volcano-name") : $("rail-btn")).focus' in WALL
    # the strip's numbers and the story's line have one source
    assert "renderRail(D, sit, caseStory);" in STORY
    assert STORY.count("allCounts(D)") >= 2


def test_the_welcome_dialog_opens_from_the_demo() -> None:
    assert _tag("welcome").startswith("<dialog")
    assert 'aria-labelledby="welcome-title"' in _tag("welcome")
    how = _tag("how-btn")
    assert 'aria-haspopup="dialog"' in how
    assert 'aria-controls="welcome"' in how
    assert 'aria-keyshortcuts="W"' in how
    assert 'class="tn-how"' in how
    assert 'import { shouldOpenWelcome, openWelcome } from "./wall/welcome.js";' in WALL
    assert "shouldOpenWelcome(params, START_HASH)" in WALL
    assert "const START_HASH = location.hash;" in WALL
    # the Wall's shortcuts are off while it is open
    assert '$("dlg").open || $("board").open || welcome().open' in WALL


def test_the_status_line_and_the_keys_have_w_e_and_a() -> None:
    footer = INDEX[INDEX.index("<footer") : INDEX.index("</footer>")]
    assert (
        footer.index("<kbd>W</kbd>How it works")
        < footer.index("<kbd>E</kbd>Story")
        < footer.index("<kbd>A</kbd>Assistant")
    )
    assert 'k === "w" || k === "W"' in WALL
    assert 'k === "e" || k === "E"' in WALL
    assert "if (!ASSISTANT_PAGE) { showAssist({ focus: true }); return; }" in WALL


def test_deep_links_open_details_on_the_demo() -> None:
    assert 'location.assign(`/demo#details-${sec || "index"}`)' in WALL
    assert 'START_HASH === "#track-record" ? "proof"' in WALL


def test_the_phone_sheet_and_the_night_map() -> None:
    assert "night" in _tag("map-pane").split('class="', 1)[1].split('"', 1)[0].split()
    phone = CSS[CSS.index("/* ---- 900 px and below:") :]
    assert "@media (max-width: 900px) {" in phone
    for rule in (
        '.side[data-sheet="half"] { height: 58vh; }',
        '.side[data-sheet="full"]',
        "height: 30vh;",
        ".side__handle { display: grid;",
    ):
        assert rule in phone, rule
    assert 'aria-controls="side"' in _tag("side-handle")
    assert 'const SHEETS = ["peek", "half", "full"];' in WALL
    # the map reads its colours from the night subtree in both themes
    basemap = (WEB / "wall" / "basemap.js").read_text(encoding="utf-8")
    assert 'document.querySelector(".night")' in basemap
    assert "mapTokens()" in (WEB / "wall" / "map.js").read_text(encoding="utf-8")


def test_the_assistant_page_stays_dark() -> None:
    mode = (WEB / "page-mode.js").read_text(encoding="utf-8")
    assert 'if (assistant) document.documentElement.dataset.theme = "dark";' in mode


def test_the_shot_map_class_shows_the_map_alone() -> None:
    assert "body.shot-map" in CSS
    rule = CSS[CSS.index("body.shot-map > .cmdbar") :].split("\n", 1)[0]
    for part in (".rail", ".story", ".side", ".timebar", ".honesty"):
        assert part in rule, part


def test_assistant_tab_text_goes_in_as_text() -> None:
    for name in ("assist.js", "assist-panel.js"):
        source = (WEB / "wall" / name).read_text(encoding="utf-8")
        assert "innerHTML" not in source, name
        assert "insertAdjacentHTML" not in source, name
    panel = (WEB / "wall" / "assist-panel.js").read_text(encoding="utf-8")
    assert 'import { stepsList, setCurrentStep, FIVE_STEPS } from "../five-steps.js";' in panel
    assert "No steps yet in this window." in panel
    assert "SAY_EVERY_MS = 10000" in panel


def test_the_strip_says_its_numbers_count_every_volcano() -> None:
    """The strip sits under one volcano's name and area while its numbers count all volcanoes
    (story.js allCounts), and the header's area chip counts one area: the strip names its scope."""
    scope = INDEX.split('id="rail-scope"')[1].split("\n")[0]
    assert '<span class="rail__short">All</span><span class="rail__long"> volcanoes</span>' in scope
    order = [INDEX.index(f'id="{i}"') for i in ("rail-vol", "rail-scope", "rail-exposed")]
    assert order == sorted(order)
    assert "const { active, exposed, drafts } = allCounts(D);" in STORY
