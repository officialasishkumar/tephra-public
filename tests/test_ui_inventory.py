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
    "replay-banner",
    "replay-banner-text",
    "replay-banner-case",
    "mode-badge",
    "regions",
    "region-select",
    "kpi-exposed",
    "kpi-active",
    "kpi-drafts",
    "ai-chip",
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
    "disclaimer",
    "attribution",
    "policy-btn",
    "help-btn",
    "about-btn",
    "dlg",
    "story",
    "details",
    "details-btn",
    "details-title",
    "story-notes",
    "trust",
    "details-sheet",
    "cta-sticky",
    "story-strip",
    "time-pill",
    # AI at work (UI-DESIGN 7.21)
    "board",
    "board-title",
    "board-status",
    "board-body",
    "board-live",
]
WALL_CLASSES = ["desk-link", "brand", "brand__sub", "honesty__airline", "map-vignette", "map-scrim"]
DESK_IDS = [
    "dhead",
    "model-chip",
    "budget-chip",
    "conn",
    "replay-bar",
    "disclaimer",
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
    "firstuse",
]
DESK_TABS = ["queue", "ask", "network", "docs"]
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
HONESTY = [
    "Decision support only - fictional airline - not for operational use",
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


def test_replay_is_labelled_once_in_the_frame_strip() -> None:
    """CLAUDE.md "REPLAY is always labelled", said once (UI-DESIGN 7.1): on the Wall and the Desk
    one frame strip (role=note) holds the REPLAY words and the disclaimer; the story, the Details
    sections, the board, the Desk's cards and reviews no longer repeat it."""
    index = (WEB / "index.html").read_text(encoding="utf-8")
    start = index.index('<div id="frame"')
    strip = index[start : index.index("</div>", start)]
    for part in ('role="note"', 'id="replay-banner"', 'id="disclaimer"', "not live"):
        assert part in strip, part
    assert index.count('id="replay-banner"') == 1
    assert index.count('id="disclaimer"') == 1
    desk = (WEB / "desk.html").read_text(encoding="utf-8")
    # the Desk's strip is the same strip, the header's top row (above the brand row)
    band = desk[desk.index('<div id="frame"') : desk.index('<div class="dhead__row"')]
    parts = ('role="note"', 'class="frame"', 'id="replay-bar"', 'id="disclaimer"')
    parts += ("not live", "#i-info")
    for part in parts:
        assert part in band, part
    assert desk.index('<div id="frame"') < desk.index('<div class="dhead__row"')
    # its accessible name follows the mode on both pages ("Disclaimer" live)
    assert "stripLabel(" in _text([WEB / "wall" / "panels.js"])
    assert "stripLabel(" in _text([WEB / "desk.js"])
    # both pages word it from one function
    assert "replayWords(" in _text([WEB / "wall" / "panels.js"])
    assert "replayWords(" in _text([WEB / "desk.js"])
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
    assert wall.count("describeModal(") >= 4  # the definition, the Details sheet, the board, #dlg
    ui = (WEB / "desk" / "ui.js").read_text(encoding="utf-8")
    assert "describeReplayIn(dlg);\n  if (!dlg.open) dlg.showModal();" in ui
    account = (WEB / "desk" / "account.js").read_text(encoding="utf-8")
    assert "describeReplayIn(dialog);\n  dialog.showModal();" in account


def test_the_frame_strip_stays_on_screen_over_dialogs_and_sheets() -> None:
    """The strip is never covered or dimmed: the phone Wall keeps it sticky, and every dialog,
    the board and the Desk's sheets open below it with their backdrop starting there."""
    wall_css = (WEB / "wall.css").read_text(encoding="utf-8")
    assert ".dlg, .board { top: var(--frame-px, 0px); }" in wall_css
    assert ".dlg::backdrop, .board::backdrop { top: var(--frame-px, 0px); }" in wall_css
    assert re.search(r"\.frame \{ position: sticky; top: 0;", wall_css)
    desk_css = (WEB / "desk.css").read_text(encoding="utf-8")
    backdrop = r"\.dlg::backdrop,\s*\.bsheet::backdrop \{\s*top: var\(--dframe-h, 0px\);"
    assert re.search(backdrop, desk_css)
    assert "--dframe-h" in (WEB / "desk.js").read_text(encoding="utf-8")


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
