"""The five steps of how TEPHRA works (SPEC-v2 3.3): said once, in ``tephra/web/five-steps.js``,
and drawn from there by the Guide, the demo's welcome dialog, the side panel and Home (its picture
and strip; tests/test_home_web.py). Source checks; the browser draws them."""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
SOURCE = (WEB / "five-steps.js").read_text(encoding="utf-8")
STEP = re.compile(
    r'\{ key: "(\w+)", icon: "([\w-]+)", name: "([^"]+)", short: "([^"]+)", line: "([^"]+)" \}'
)
STEPS = STEP.findall(SOURCE)
WEB_TREE = [p for p in WEB.rglob("*") if p.suffix in {".js", ".html"} and p.is_file()]


def test_there_are_five_steps_in_order() -> None:
    assert [(key, name, short) for key, _, name, short, _ in STEPS] == [
        ("feeds", "Public feeds", "Feeds"),
        ("code", "Code checks", "Checks"),
        ("ai", "TEPHRA Assistant", "Assistant"),
        ("desk", "A person decides", "You decide"),
        ("record", "The record", "Record"),
    ]


@pytest.mark.parametrize("line", [step[4] for step in STEPS])
def test_each_step_s_line_is_said_once_in_the_web_tree(line: str) -> None:
    hits = {
        p.relative_to(WEB).as_posix(): p.read_text(encoding="utf-8").count(line) for p in WEB_TREE
    }
    found = {name: n for name, n in hits.items() if n}
    assert found == {"five-steps.js": 1}, found


def test_every_step_icon_is_in_the_sprite() -> None:
    sprite = (WEB / "icons.svg").read_text(encoding="utf-8")
    for _, icon, *_ in STEPS:
        assert f'id="{icon}"' in sprite, icon


@pytest.mark.parametrize(
    ("rel", "spec"),
    [
        ("guide.js", "./five-steps.js"),
        ("wall/welcome.js", "../five-steps.js"),
    ],
)
def test_the_guide_and_the_welcome_draw_them(rel: str, spec: str) -> None:
    source = (WEB / rel).read_text(encoding="utf-8")
    assert re.search(rf'import \{{[^}}]*\bstepsList\b[^}}]*\}} from "{re.escape(spec)}";', source)


def test_the_guide_has_no_copy_of_its_own() -> None:
    guide = (WEB / "guide.html").read_text(encoding="utf-8")
    assert '<div id="gpipe" class="gpipe-host"></div>' in guide
    assert 'class="gpipe"' not in guide
    assert 'href="/static/five-steps.css"' in guide
    # the names only; the lines stay for screen readers (TEXT-SPEC G1)
    assert 'document.getElementById("gpipe").replaceChildren(stepsList({ lines: "sr" }));' in (
        WEB / "guide.js"
    ).read_text(encoding="utf-8")
    assert 'class: lines === "sr" ? "sr-only" : "steps5__line"' in SOURCE
    assert ".gpipe__n" not in (WEB / "guide.css").read_text(encoding="utf-8")


def test_the_markup_numbers_each_step_for_a_screen_reader_and_rings_the_current() -> None:
    assert '"aria-hidden": "true", text: n' in SOURCE
    assert 'el("span", { class: "sr-only", text: `Step ${n}: ` })' in SOURCE
    assert 'li.setAttribute("aria-current", "step")' in SOURCE
    assert "innerHTML" not in SOURCE


def test_the_badges_are_neutral_ink_and_the_strip_stacks_on_a_phone() -> None:
    css = (WEB / "five-steps.css").read_text(encoding="utf-8")
    badge = css[css.index(".steps5__num {") : css.index("}", css.index(".steps5__num {"))]
    assert "background: var(--c-text-1);" in badge
    assert "color: var(--c-bg);" in badge
    assert "@media (max-width: 759px)" in css
    for key in ("feeds", "code", "ai", "desk", "record"):
        assert f".steps5__n--{key} {{ --tone: var(--tone-{key}); }}" in css, key
