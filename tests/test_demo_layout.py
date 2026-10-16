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
    "assist-inside",
    "assist-what-h",
    "assist-player",
    "assist-note",
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
# the Assistant tab's small five-step row and its "Now" card went on 16 Oct 2026: the Inside TEPHRA
# diagram shows where the newest step is and what it did
GONE = [
    "ai-chip",
    "details-sheet",
    "cta-sticky",
    "panel-toggle",
    "phone-bar",
    "story-strip",
    "assist-pipe",
    "assist-now",
]


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
    """The owner (16 Oct 2026): Assistant leaves the top nav; /assistant is reached from the side
    panel's pop-out icon (#assist-page) and the Guide."""
    nav = (
        '<nav class="topnav" aria-label="TEPHRA pages"><a href="/demo" aria-current="page">Demo</a>'
        '<a class="topnav__keep" href="/desk">Desk</a>'
        '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>'
        '<a href="/guide">Guide</a></nav>'
    )
    assert nav in INDEX
    assert 'href="/assistant">Assistant</a>' not in INDEX
    assert '.topnav a[href="/assistant"]' not in WALL
    assert '.topnav a[href="/assistant"]' not in CSS
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
    # under the Assistant tab the diagram's You decide says the foot's words: the foot keeps only
    # its button there, and the diagram draws no second Desk button (board-view.js mountInside)
    assert 'side.classList.toggle("is-assist", !det);' in WALL
    assert ".side.is-assist .side__eyebrow, .side.is-assist .side__line { display: none; }" in CSS
    view = (WEB / "wall" / "board-view.js").read_text(encoding="utf-8")
    assert "...(side ? [] : [factsCap, facts," in view
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
    assert 'import { mountInside, drawInside, insideColours, SRC } from "./board-view.js";' in panel
    assert "mountInside({ has, side: true })" in panel
    assert "No steps yet in this window." in panel
    assert "SAY_EVERY_MS = 10000" in panel


def test_the_assistant_tab_is_the_state_the_diagram_then_what_happened() -> None:
    """The owner (16 Oct 2026): the /assistant page's Inside TEPHRA panel in the demo's right
    panel, under the state line, then What happened: the step log, folded to its newest rows with
    "Show all". The player ("Replay · ...") sits above the diagram, so the catch-up's label shows
    on a 1366x768 or 1280x720 laptop too (batch 2 UX finding 1); it is held at the top of the tab
    while the catch-up plays."""
    start = INDEX.index('<section id="assist" ')
    tab = INDEX[start : INDEX.index('id="details"', start)]
    ids = ("ai-state", "assist-player", "assist-note", "assist-inside", "assist-what-h")
    order = [tab.index(f'id="{i}"') for i in (*ids, "assist-log")]
    assert order == sorted(order)
    assert ".player.is-catchup { position: sticky; top: 0;" in CSS
    assert "@media (min-width: 901px) and (max-height: 860px) {" in CSS
    assert "What happened" in tab
    panel = (WEB / "wall" / "assist-panel.js").read_text(encoding="utf-8")
    assert "const FOLDED_ROWS = 3;" in panel
    assert "`Show all (${rows.length})`" in panel
    assert '"Replay again"' in panel
    # one column on every width (the rail runs through each skill), first in the tab on a phone
    assert "order: 0; width: auto;" in CSS
    assert ".side .flow-panel--side .flow-skills { display: block; }" in CSS


def test_the_catch_up_waits_for_the_welcome_and_skips_screenshots() -> None:
    assert 'blocked: () => welcome().open || $("dlg").open,' in WALL
    assert "noCatchup: SHOTS," in WALL
    assert (
        'welcome().addEventListener("close", () => requestAnimationFrame(() => assist?.poke()));'
        in WALL
    )


def test_the_pulses_never_take_a_click_and_hide_in_forced_colours() -> None:
    rule = CSS[CSS.index(".as-flow {") :].split("\n", 1)[0]
    assert "position: fixed" in rule
    assert "pointer-events: none" in rule
    assert '"aria-hidden": "true"' in (WEB / "wall" / "assist-panel.js").read_text(encoding="utf-8")
    forced = CSS[CSS.index("@media (forced-colors: active) {\n  .as-flow") :]
    assert ".as-flow { display: none; }" in forced.split("}", 2)[0] + "}"


def test_the_strip_says_its_numbers_count_every_volcano() -> None:
    """The strip sits under one volcano's name and area while its numbers count all volcanoes
    (story.js allCounts), and the header's area chip counts one area: the strip names its scope."""
    scope = INDEX.split('id="rail-scope"')[1].split("\n")[0]
    assert '<span class="rail__short">All</span><span class="rail__long"> volcanoes</span>' in scope
    order = [INDEX.index(f'id="{i}"') for i in ("rail-vol", "rail-scope", "rail-exposed")]
    assert order == sorted(order)
    assert "const { active, exposed, drafts } = allCounts(D);" in STORY


def test_the_catch_up_plays_only_where_it_is_seen() -> None:
    """Batch 2 (UX 2, 9; honesty 6): on a phone the catch-up waits while the sheet only peeks
    and starts when it opens; it holds between beats while the tab is hidden, a dialog covers it
    or the sheet folds, and goes on when the tab shows again."""
    panel = (WEB / "wall" / "assist-panel.js").read_text(encoding="utf-8")
    assert 'const unseen = () => !shown() || blocked() || sheet() === "peek";' in panel
    assert "if (unseen()) { CU.held = true; return; }" in panel
    assert 'if (CU.state === "playing" && CU.held && !CU.timer && !unseen()) nextBeat();' in panel
    start = WALL.index("function setSheet(state) {")
    assert "requestAnimationFrame(() => assist?.poke());" in WALL[start : start + 200]


def test_you_decide_keeps_nothing_leaves_tephra_under_the_assistant_tab() -> None:
    """The foot's line is hidden under the Assistant tab (wall.css is-assist), so the diagram's
    You decide says it: an honesty label is never removed (batch 2 honesty finding 4)."""
    view = (WEB / "wall" / "board-view.js").read_text(encoding="utf-8")
    assert '"Nothing leaves TEPHRA until a dispatcher approves."' in view
    assert ".side.is-assist .side__eyebrow, .side.is-assist .side__line { display: none; }" in CSS
