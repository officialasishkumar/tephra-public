"""Feature flags (SPEC §5.3, §6 D3; SPEC-v2 3.1): one mechanism, ``wall/features.js``, read by the
demo, the Guide, Home, onboarding and the workspace (the Desk's own import is T11's test); a nav
link names its feature in ``data-feature``; every string a hidden feature owns sits on a line
guarded by ``has("...")`` or a ``feature:`` tag, and the pinned strings stay."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
FEATURES = (
    "connect",
    "crew",
    "notices",
    "satellite",
    "btd",
    "voice",
    "example",
    "present",
    "onboard",
    "hosted",
)

# a string of a hidden feature -> (file, the feature its line must consult)
GUARDED = {
    '"Split-window BTD"': ("wall/controls.js", "btd"),
    '"Satellite boxes"': ("wall/controls.js", "satellite"),
    '"Crew report caution areas"': ("wall/controls.js", "crew"),
    '"BTD indicator on/off"': ("wall/controls.js", "btd"),
    '"Presentation layout for recording (keeps Details closed)"': ("wall/controls.js", "present"),
    'title: "Satellite picture"': ("wall/details.js", "satellite"),
    'title: "Notices"': ("wall/details.js", "notices"),
    'title: "Crew reports of ash"': ("wall/details.js", "crew"),
    'name: "Satellite reader"': ("wall/board.js", "satellite"),
    'name: "Notice reader"': ("wall/board.js", "notices"),
    'setLayer("btd", !ui.btd)': ("wall.js", "btd"),
    "setPresent(!ui.present)": ("wall.js", "present"),
}


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _line_with(source: str, needle: str) -> str:
    lines = [line for line in source.splitlines() if needle in line]
    assert len(lines) == 1, (needle, len(lines))
    return lines[0]


def test_features_js_is_the_one_mechanism() -> None:
    source = _read("wall/features.js")
    assert "export function setFeatures(list)" in source
    assert "export const has = (name) => shown.has(name);" in source
    assert "export function applyFeatureNav(root = document)" in source
    assert ".topnav a[data-feature]" in source
    assert '!has(a.dataset.feature) && a.getAttribute("aria-current") !== "page"' in source
    assert "/connect" not in source


def test_the_onboard_nav_link_is_hidden_until_the_features_say_so() -> None:
    link = '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>'
    for page in ("home.html", "guide.html", "privacy.html", "doc.html"):
        html = _read(page)
        assert link in html, page
        assert 'href="/connect"' not in html, page
        assert '<a href="/demo"' in html, page


def test_every_page_script_reads_the_server_features() -> None:
    for rel in ("wall.js", "guide.js", "home.js", "onboard.js", "workspace.js"):
        source = _read(rel)
        assert 'from "./wall/features.js"' in source, rel
        assert "setFeatures(" in source, rel
        assert "applyFeatureNav()" in source, rel
    wall = _read("wall.js")
    # on the first load and on every `state` arrival
    assert "store.state = data.state;\n    setFeatures(data.state.features);" in wall
    assert "store.state = s;\n    setFeatures(s.features);" in wall


def test_every_hidden_string_sits_on_a_guarded_line() -> None:
    for needle, (rel, feature) in GUARDED.items():
        line = _line_with(_read(rel), needle)
        guards = (f'has("{feature}")', f'feature: "{feature}"', f'"{feature}"]')
        assert any(g in line for g in guards), (rel, needle)


def test_the_index_board_and_roster_consult_the_feature() -> None:
    details = _read("wall/details.js")
    assert "if (s.hidden || (s.feature && !has(s.feature))) continue;" in details
    board_view = _read("wall/board-view.js")
    assert "const shown = (id) => !FEATURE_OF[id] || has(FEATURE_OF[id]);" in board_view
    assert 'modeSeg.hidden = !has("example");' in board_view
    # the view imports nothing that holds the Wall's state: the predicate is handed in
    assert 'from "./features.js"' not in board_view
    assert "export function mountFlow(dialog, { has })" in board_view
    assert "mountFlow(dlg, { has })" in _read("wall.js")
    ext = _read("wall/ext.js")
    assert "HELPERS.filter((h) => !h.feature || has(h.feature))" in ext
    assert "AGENTS" not in ext, "the roster is read when drawn, after the features arrive"


def test_the_shortcut_list_drops_a_hidden_features_key() -> None:
    controls = _read("wall/controls.js")
    assert "export const shortcuts = () =>" in controls
    assert "!feature || has(feature)" in controls
    assert "SHORTCUTS" not in controls


def test_a_hidden_nav_link_is_hidden_by_the_stylesheet_too() -> None:
    # .topnav a sets display, which would win over the hidden attribute
    assert ".topnav a[hidden] { display: none; }" in _read("topnav.css")


def test_the_pinned_strings_stay_in_source() -> None:
    assert "Split-window BTD" in _read("wall/controls.js")
    assert "never smaller than the official area" in _read("wall/controls.js")
    assert "The Gemini Plume reader" in _read("wall/ext.js")
    assert "Satellite reader and Plume reader" in _read("wall/duty.js")
    pages = _read("wall/duty.js") + _read("wall/ext.js")
    assert not re.search(r"Plume Reader|Satellite Reader|Notice Reader", pages)


def test_the_feature_names_match_the_contract() -> None:
    config = (WEB.parent / "config.py").read_text(encoding="utf-8")
    names = re.search(r"Feature = Literal\[(.*?)\]", config, re.S)
    assert names
    assert tuple(re.findall(r'"([a-z]+)"', names.group(1))) == FEATURES
    used = set()
    files = (
        "wall.js",
        "wall/controls.js",
        "wall/details.js",
        "wall/board.js",
        "wall/board-view.js",
    )
    for rel in (*files, "wall/ext.js", "wall/features.js", "home.js", "guide.js"):
        used.update(re.findall(r'(?<![.\w])has\("([a-z]+)"\)', _read(rel)))
        used.update(re.findall(r'feature: "([a-z]+)"', _read(rel)))
    assert used <= set(FEATURES), used - set(FEATURES)
