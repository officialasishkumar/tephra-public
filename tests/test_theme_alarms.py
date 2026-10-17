"""Red is for real alarms only; dashed means not real or not connected.

See docs/UI-DESIGN.md 3.1, 3.2 and 7.34.

Theme "Basalt & Paper", 17 Oct 2026. A SERIOUS discrepancy, a failed check, a form error and a
decision are not alarms: they use caution, --c-invalid or a neutral, each with its shape and words.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _rule(css: str, selector: str) -> str:
    """The body of the first rule whose selector list contains `selector`."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
        if selector in [s.strip() for s in m.group(1).split(",")]:
            return m.group(2)
    raise AssertionError(selector)


def test_the_warning_tone_is_caution_with_the_triangle() -> None:
    assert 'warning: ["st-caution", "var(--c-caution)"]' in _read("wall/dk.js")


def test_non_alarms_on_the_wall_use_warning_not_serious() -> None:
    panels = _read("wall/panels.js")
    assert 'WARNING: ["warning", "Serious"]' in panels
    assert '? "warning" : "caution"' in panels
    ext = _read("wall/ext.js")
    assert 'REJECTED: ["off", "Rejected"]' in ext
    assert 'FAIL: "warning"' in ext
    assert 'tt.cancelled_flights ? "warning"' in ext
    assert 'worst >= 3 ? "warning"' in _read("wall/details.js")


def test_form_errors_use_invalid_never_the_alarm_red() -> None:
    desk = _read("desk.css")
    for sel in (".msg--invalid", ".panel--invalid"):
        body = _rule(desk, sel)
        assert "--c-invalid" in body, sel
        assert "--c-serious" not in body, sel
    product = _read("product.css")
    assert "--c-invalid" in _rule(product, ".err")
    review = _read("desk/review.js")
    check_line = "class: 'msg msg--invalid' }, icon('st-caution', 'st'), el('span', { text: `Check"
    assert check_line in review


def test_not_real_or_not_connected_chips_are_dashed() -> None:
    product = _read("product.css")
    for sel in (".chip--nomodel", ".chip--example"):
        assert "dashed" in _rule(product, sel), sel
    wall = _read("wall.css")
    assert "dashed" in _rule(wall, ".dk-chip--illustrative")
    # the assistant's one status when off (the tab bar and the /assistant board)
    assert "dashed" in _rule(wall, '.side__ai[data-tone="off"] .side__ai-word')
    assert "dashed" in _rule(wall, '.flow-head__status[data-tone="off"] .flow-head__word')


def test_desk_field_errors_are_invalid_with_the_triangle() -> None:
    html = _read("desk.html")
    for fid in ("visitor-name-err", "login-name-err", "login-pin-err"):
        assert f'<p id="{fid}" class="msg msg--invalid" hidden></p>' in html, fid
    login = _read("desk/login.js")
    assert "field ? ['msg--invalid', 'st-caution']" in login
    review = _read("desk/review.js")
    invalid = "el('p', { class: 'msg msg--invalid' }, icon('st-caution', 'st'), el('span', { text: "
    for v in ("sheet.crewError", "sheet.error"):
        assert f"{invalid}{v} }}))" in review, v
    crew = _read("desk/crew.js")
    assert "replaceChildren(...(text ? [invalidLine(text)] : []))" in crew
    assert "invalidLine('Not recorded yet: check the fields marked below.')" in crew
    assert "class: 'msg msg--invalid'" in _read("desk/connections.js")
    for rel in ("desk/docs.js", "desk/network.js"):
        assert "res.status === 422 ? ['msg--invalid', 'st-caution']" in _read(rel), rel


def test_a_failed_specialist_call_is_caution_not_red() -> None:
    desk = _read("desk.css")
    for sel in (".dcard__d--bad", ".dcard__d--bad .dcard__arrow"):
        body = _rule(desk, sel)
        assert "--c-caution" in body, sel
        assert "--c-serious" not in body, sel


def test_line_grammar_solid_real_dashed_not_connected_or_example() -> None:
    desk = _read("desk.css")
    assert "dashed" in _rule(desk, '.budget[data-tone="off"]')
    assert "dashed" in _rule(desk, ".chip--fict")
    assert "dashed" in _rule(desk, ".swatch--tephra")
    assert "dashed" in _rule(_read("wall.css"), ".dk-pill--off")
    recov = _rule(_read("product.css"), ".recov")
    assert "solid" in recov
    assert "dashed" not in recov
    assert "{ open: true }" in _read("wall/images.js")


def test_the_home_flow_is_one_neutral_dotted_wire() -> None:
    body = _rule(_read("home.css"), ".how__path")
    assert "--c-line-input" in body
    assert "dasharray" in body
    assert "url(" not in body
    assert "linearGradient" not in _read("home/how.js")


def test_catch_up_pulses_from_the_map_take_the_night_colours() -> None:
    panel = _read("wall/assist-panel.js")
    assert "CM[kind] || CM.info" in panel
    assert 'class: "as-flow__lab night"' in panel
    assert 'document.querySelector(".map-pane.night")' in _read("wall/board-view.js")
