"""The "nothing deleted" checklist (docs/UI-REDESIGN.md R17.1, G18).

The redesign reorganises the Wall and the Desk: nothing on screen before it may be lost. This
static test (no browser) checks that every id, section and builder the spec lists still exists in
the page sources, that the honesty strings are still there, and that the things the redesign
removed for good (stacked map labels, sub-12 px text, the stored empty-region flag) stay gone.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
WALL_FILES = [WEB / "index.html", WEB / "wall.js", *sorted((WEB / "wall").glob("*.js"))]
DESK_FILES = [WEB / "desk.html", WEB / "desk.js", *sorted((WEB / "desk").glob("*.js"))]


def _text(files: list[Path]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in files)


WALL = _text(WALL_FILES)
DESK = _text(DESK_FILES)
ALL = WALL + "\n" + DESK

# R11.1-R11.4, plus the ids the spec's checks name. Every id stays; nodes were re-parented.
WALL_IDS = [
    "mode-badge",
    "regions",
    "region-select",
    "kpi-exposed",
    "kpi-active",
    "kpi-drafts",
    "model-chip",
    "feeds-chip",
    "clock-time",
    "clock-sub",
    "stale-chip",
    "lost-banner",
    "verdict",
    "headline",
    "map-notes",
    "ctx-label",
    "compare-labels",
    "legend",
    "tools",
    "layers-pop",
    "levels",
    "trace",
    "flights",
    "timeline",
    "xtabs",
    "xpanel",
    "volcano-tabs",
    "brief",
    "volcano-name",
    "decisions",
    "announce",
    "attribution",
    "policy-btn",
    "help-btn",
    "dlg",
    "story",
    "details",
    "details-btn",
    "details-title",
    "story-notes",
    "trust",
    "time-pill",
    # the demo's layout (SPEC v2 3.5): the welcome dialog, the slim story strip, the side panel
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
    "story-fold",
    "side",
    "side-tabs",
    "assist-tab",
    "assist-page",
    "assist",
    "ai-state",
    "assist-player",
    "assist-inside",
    "assist-what-h",
    "assist-note",
    "assist-log",
    "assist-live",
    "side-foot",
    "side-desk",
    "side-handle",
    # AI at work (UI-DESIGN 7.21)
    "board",
    "board-title",
    "board-status",
    "board-body",
    "board-live",
]
# the Desk link is in the shared nav (UI-DESIGN 7.25), kept on a narrow Wall as topnav__keep
WALL_CLASSES = [
    "topnav__keep",
    "brand",
    "brand__sub",
    "honesty__airline",
    "map-vignette",
    "map-scrim",
]
DESK_IDS = [
    "dhead",
    "model-chip",
    "budget-chip",
    "conn",
    "net-banner",
    "q-title",
    "paste-notice",
    "refresh",
    "duty-section",
    "fail-section",
    "drafts-title",
    "q-count",
    "cards",
    "msg-section",
    "plan-section",
    "notice-section",
    "closed",
    "sheet",
    "panel-ask",
    "panel-network",
    "panel-docs",
    "tabbar",
    "toasts",
    "announcer",
    "display-dialog",
    "bsheet",
    # R10: the redesign's own pieces
    "q-more-btn",
    "q-more",
    "q-breakdown",
    "q-newer",
    "q-next",
    "more-title",
    "closed-count",
    "login-pending",
    "net-title",
    "docs-title",
    "ask-title",
    "why",
    # Desk redesign (UI-DESIGN 10.16): the flights to plan by hand, the idle right pane
    "fail-pane",
    "fp-title",
    "idle-pane",
    "idle-title",
    # Desk redesign (UI-DESIGN 10.17): the inbox groups, the receipt line, the first-use line
    "watch-section",
    "other-section",
    "receipt",
]
# Ask left the tab bar for the header's Ask drawer (UI-DESIGN 10.18)
DESK_TABS = ["queue", "network", "docs"]
# R8.3: every Details section key
SECTION_KEYS = [
    "sources",
    "disagree",
    "estimate",
    "sat",
    "notices",
    "flights",
    "decisions",
    "recovery",
    "history",
    "levels",
    "trace",
    "ai",
    "proof",
    "feeds",
    "layers",
    "area",
    "flight",
]
# One assertion per old panel section: the builder or its tell-tale string is still there.
BUILDERS = {
    "sources grid, SIGMET column": "SIGMET (airspace warning)",
    "sources grid, VAA column": "VAA (ash advisory)",
    "sources grid, VONA column": "VONA (volcano observatory notice)",
    "sources grid, raw text": '"Raw text"',
    "sources grid, hash": "sha256_short",
    "disagreement list with minor differences": "Minor differences (",
    "TEPHRA area card": "export function areaSection",
    "satellite image": "x-frame__img",
    "satellite SO2": "Gas (SO2, not ash)",
    "BTD": "Split-window BTD",
    "notices with claims": "All notices and their claims",
    "recovery scenario table": "Recovery scenarios",
    "recovery per-airport reason": "Full reason and sources",
    "backtest per-case table": "Backtest results per case",
    "Duty Officer delegation diagram": "Delegation diagram",
    "budget tiers": "x-tier",
    "feed rows": "feeds__row",
    "policy values table": "Operator policy values",
    "glossary": "help__glossary",
    "credits table": 'text: "Credits"',
    "reasoning trace raw line": "Technical detail",
    "flights list": "export function renderFlights",
    "decisions list": "export function decisionsSection",
    "level filter": "export function renderLevels",
    "timeline lanes": "When each source last reported",
    "sources side by side dialog": "export function sourcesDialog",
    "AI at work board": "export function boardModel",
    # the flow board (UI-DESIGN 7.21) draws each hand-out as a token down the AI lane
    "AI at work hand-out lines": "function drawRails(",
    "AI at work flow board": "export function flowModel",
}
# the top strip with the disclaimer was removed at the owner's request (15 Oct 2026, UI-DESIGN 7.1)
HONESTY = [
    "CONTEXT ONLY",
    "HYPOTHESIS",
    "never smaller",
    "Approved text goes only to TEPHRA's own outbound queue",
    "RFA",
    "fictional",
]


def _has_id(source: str, ident: str) -> bool:
    i = re.escape(ident)
    pattern = rf"""id=["']{i}["']|id:\s*["']{i}["']|\$\(["']{i}["']\)"""
    return bool(re.search(pattern, source))


@pytest.mark.parametrize("ident", WALL_IDS)
def test_wall_ids_are_kept(ident: str) -> None:
    assert _has_id(WALL, ident), ident


@pytest.mark.parametrize("cls", WALL_CLASSES)
def test_wall_classes_are_kept(cls: str) -> None:
    assert re.search(rf"""class=["'][^"']*\b{re.escape(cls)}\b""", WALL), cls


@pytest.mark.parametrize("ident", DESK_IDS)
def test_desk_ids_are_kept(ident: str) -> None:
    assert _has_id(DESK, ident), ident


def test_desk_tab_keys_are_kept() -> None:
    for key in DESK_TABS:
        assert f"'{key}'" in DESK or f'"{key}"' in DESK, key


def test_every_details_section_key_exists() -> None:
    details = (WEB / "wall" / "details.js").read_text(encoding="utf-8")
    table = details[details.index("export const SECTIONS") : details.index("const HOSTS")]
    for key in SECTION_KEYS:
        assert f'key: "{key}"' in table, key


def test_old_rail_panel_ids_still_open_their_section() -> None:
    details = (WEB / "wall" / "details.js").read_text(encoding="utf-8")
    for xtab in ("brief", "sat", "notices", "recovery", "proof", "ai"):
        assert f'xtab: "{xtab}"' in details, xtab


@pytest.mark.parametrize("name", BUILDERS)
def test_every_old_panel_section_has_its_builder(name: str) -> None:
    assert BUILDERS[name] in WALL, name


@pytest.mark.parametrize("text", HONESTY)
def test_honesty_strings_are_kept(text: str) -> None:
    assert text in ALL, text


def test_replay_is_labelled_by_the_page_not_a_strip() -> None:
    """The top strip (REPLAY words and the disclaimer) was removed at the owner's request on
    15 Oct 2026 (UI-DESIGN 7.1). REPLAY stays in each page's title, the Wall's clock and status dot,
    and every modal's sr-only description; records do not repeat it."""
    for page in ("index.html", "desk.html", "guide.html"):
        html = (WEB / page).read_text(encoding="utf-8")
        assert 'id="frame"' not in html, page
        assert "tn-strip" not in html, page
    panels = _text([WEB / "wall" / "panels.js"])
    assert '`${replay ? "REPLAY - " : ""}TEPHRA ${' in panels
    assert '"Replay clock · "' in panels
    assert 'replay: "Replay"' in panels
    assert "'REPLAY - '" in _text([WEB / "desk.js"])
    # the modals' sr-only REPLAY words come from one function on both pages
    assert "replayWords(" in panels
    assert "replayWords(" in _text([WEB / "desk" / "ui.js"])
    # the second labels are gone from the main views
    for gone in ("dkRecorded", "eyebrow__rec", "board__replay", "replayBand", "mode-badge--replay"):
        assert gone not in WALL, gone
    for gone in ("replayChip", "Drafted from recorded feeds", "replay-bar__auto"):
        assert gone not in DESK, gone


def test_a_record_from_the_other_mode_keeps_one_tag() -> None:
    """The strip says what plays, so a replay record seen while live feeds play keeps a tag, worded
    "From a replay" everywhere; the Desk's review and Next decision card carry it too (a replay
    draft opened from a link while live feeds play is otherwise unlabelled)."""
    assert 'text: "From a replay"' in WALL
    assert "text: 'From a replay'" in DESK
    for gone in ('"from a replay"', '"entered in REPLAY"', 'text: "recorded" }'):
        assert gone not in WALL, gone
    review = (WEB / "desk" / "review.js").read_text(encoding="utf-8")
    assert "fromReplayChip(adv)" in review
    queue = (WEB / "desk" / "queue.js").read_text(encoding="utf-8")
    assert "fromReplayChip(adv)" in queue
    # before the state loads the mode is unknown: no chip, never a flash of it in REPLAY
    ui = (WEB / "desk" / "ui.js").read_text(encoding="utf-8")
    assert "!app.state || app.state.mode === 'REPLAY'" in ui


def test_every_modal_carries_the_replay_words_for_screen_readers() -> None:
    """A modal dialog makes the strip inert, so each modal on the Wall and the Desk gets the strip's
    REPLAY words as sr-only text in its description (no visible label)."""
    wall = (WEB / "wall.js").read_text(encoding="utf-8")
    assert wall.count("describeModal(") >= 3  # the definition, the board, #dlg
    # the welcome dialog gets them from wall/welcome.js openWelcome (describeReplay)
    assert "describeReplay(" in (WEB / "wall" / "welcome.js").read_text(encoding="utf-8")
    ui = (WEB / "desk" / "ui.js").read_text(encoding="utf-8")
    assert "describeReplayIn(dlg);\n  if (!dlg.open) dlg.showModal();" in ui
    account = (WEB / "desk" / "account.js").read_text(encoding="utf-8")
    assert "describeReplayIn(dialog);\n  dialog.showModal();" in account


def test_wall_trust_line_says_never_smaller() -> None:
    """docs/UI-AI-QUIET.md W17, 2.2: the trust line keeps the floor in every AI state."""
    assert "never smaller than the official area" in WALL


def test_only_the_selected_official_label_may_overlap() -> None:
    """R6.3, G3: every other map label collides, so labels never stack again."""
    for path in (WEB / "wall" / "map.js", WEB / "wall" / "ext-map.js"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if '"text-allow-overlap": true' in line:
                assert 'id: "official-label-selected"' in line, line.strip()[:120]


def _small_font_sizes(css: str) -> list[str]:
    found = []
    for match in re.finditer(r"font-size:\s*([0-9.]+)(px|rem)", css):
        value, unit = float(match.group(1)), match.group(2)
        px = value if unit == "px" else value * 16
        if px < 12:
            found.append(match.group(0))
    return found


def test_wall_css_has_no_text_under_12_px() -> None:
    assert _small_font_sizes((WEB / "wall.css").read_text(encoding="utf-8")) == []


def test_map_labels_are_at_least_12_px() -> None:
    for path in (WEB / "wall" / "map.js", WEB / "wall" / "ext-map.js"):
        source = path.read_text(encoding="utf-8")
        sizes = [float(s) for s in re.findall(r'"text-size":\s*([0-9.]+)', source)]
        assert sizes, path.name
        assert min(sizes) >= 12, (path.name, sizes)


def test_region_emptiness_is_derived_not_stored() -> None:
    """R2.1: the stored flag made the area chip and the story disagree."""
    assert "emptyRegion" not in WALL


def test_desk_css_has_no_text_under_12_px() -> None:
    assert _small_font_sizes((WEB / "desk.css").read_text(encoding="utf-8")) == []


def test_doc_css_has_no_text_under_12_px() -> None:
    """The Desk links doc.css too (R15.3)."""
    assert _small_font_sizes((WEB / "doc.css").read_text(encoding="utf-8")) == []


def test_desk_tab_labels_are_the_new_words() -> None:
    """R10.2: only the labels changed; the keys stayed."""
    tabs = (WEB / "desk" / "tabs.js").read_text(encoding="utf-8")
    assert "queue: 'Decide'" in tabs
    assert "network: 'Airports'" in tabs
    assert "docs: 'Paperwork'" in tabs


def test_desk_has_no_bulk_approval_and_keeps_hold_and_confirm() -> None:
    """R0.2 rule 11, G16: one decision per advisory; the deep link is only a pointer."""
    assert "Approve all" not in DESK
    assert "Hold to approve, or tap to confirm." in DESK
    assert "Approve now" in DESK


def test_desk_duty_card_never_appends_a_null() -> None:
    source = (WEB / "desk" / "duty.js").read_text(encoding="utf-8")
    assert not re.search(r"card\.append\([^;]*\?[^;]*:\s*null", source, re.S)
