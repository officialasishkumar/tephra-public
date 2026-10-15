"""The Guide's annotated screenshots (UI-DESIGN 7.29): every shot the page names is a file and an
entry in data/guide-shots.json, the image size in the markup is the file's, every mark has its
legend item and every legend item its mark, and the marks sit inside the image. The legend speaks
the way the UI does (CLAUDE.md "How the UI talks"). Source checks only; the browser draws the page.
"""

import json
import re
from pathlib import Path

import pytest
from PIL import Image

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
GUIDE = (WEB / "guide.html").read_text(encoding="utf-8")
SHOT_JS = (WEB / "guide" / "shot.js").read_text(encoding="utf-8")
SHOTS = json.loads((WEB / "data" / "guide-shots.json").read_text(encoding="utf-8"))
SHOT_DIR = WEB / "guide" / "shots"
MAX_BYTES = 250_000

FIGURE = re.compile(r'<figure class="shot[^"]*" data-shot="([^"]+)">(.*?)</figure>', re.S)
ITEM = re.compile(
    r'<button type="button" class="shot__item" data-n="(\d+)">'
    r'<span class="shot__num" aria-hidden="true">(\d+)</span>'
    r'<span class="shot__txt"><b>([^<]+)</b><span>([^<]+)</span></span></button>'
)
IMG = re.compile(
    r'<img class="shot__img" src="/static/guide/shots/([^"]+)\.webp" width="(\d+)" height="(\d+)"'
)

FIGURES = dict(FIGURE.findall(GUIDE))


def _items(name: str) -> list[tuple[int, str, str]]:
    found = ITEM.findall(FIGURES[name])
    for n, shown, _, _ in found:
        assert n == shown, (name, n, shown)
    return [(int(n), title, body) for n, _, title, body in found]


def test_the_guide_tours_each_page() -> None:
    assert list(FIGURES) == ["wall", "assistant", "desk", "desk-phone", "connect"]
    assert set(SHOTS) == set(FIGURES), "guide-shots.json and the guide name the same shots"
    on_disk = {p.stem for p in SHOT_DIR.glob("*.webp")}
    assert on_disk == set(FIGURES), "no screenshot file without its figure, nor the reverse"


@pytest.mark.parametrize("name", list(FIGURES))
def test_each_shot_is_a_file_of_the_size_the_markup_says(name: str) -> None:
    img = IMG.search(FIGURES[name])
    assert img, name
    assert img.group(1) == name
    path = SHOT_DIR / f"{name}.webp"
    assert path.stat().st_size <= MAX_BYTES, (name, path.stat().st_size)
    with Image.open(path) as im:
        assert im.format == "WEBP"
        assert im.size == (SHOTS[name]["w"], SHOTS[name]["h"])
    assert (int(img.group(2)), int(img.group(3))) == (SHOTS[name]["w"], SHOTS[name]["h"])


@pytest.mark.parametrize("name", list(FIGURES))
def test_every_mark_has_its_legend_item_and_every_item_its_mark(name: str) -> None:
    marks = SHOTS[name]["marks"]
    numbers = [m["n"] for m in marks]
    assert numbers == list(range(1, len(marks) + 1)), name
    assert 4 <= len(marks) <= 8, name
    assert [n for n, _, _ in _items(name)] == numbers, name


@pytest.mark.parametrize("name", list(FIGURES))
def test_the_marks_sit_inside_the_image(name: str) -> None:
    for m in SHOTS[name]["marks"]:
        assert set(m) <= {"n", "x", "y", "w", "h", "pin"}, m
        for key in ("x", "y", "w", "h"):
            assert 0 <= m[key] <= 100, (name, m)
            assert round(m[key], 2) == m[key], (name, m)
        assert m["w"] > 0, (name, m)
        assert m["h"] > 0, (name, m)
        assert m["x"] + m["w"] <= 100.01, (name, m)
        assert m["y"] + m["h"] <= 100.01, (name, m)


@pytest.mark.parametrize("name", list(FIGURES))
def test_the_legend_is_short_and_in_the_product_s_words(name: str) -> None:
    for n, title, body in _items(name):
        assert 1 <= len(title.split()) <= 5, (name, n, title)
        # one short sentence: a single full stop, at the end
        assert body.endswith("."), (name, n, body)
        assert body.count(". ") == 0, (name, n, body)
        assert len(body) <= 80, (name, n, body)
        words = f"{title} {body}"
        assert not re.search(r"\bAI\b|quota|budget|model id|gemini|a day", words, re.I), words


def test_marks_are_named_buttons_and_the_numbers_are_info_coloured() -> None:
    assert 'el("button", { type: "button", class: `shot__mark' in SHOT_JS
    assert '"aria-label": `${m.n}: ${titleOf(m.n)}`' in SHOT_JS
    css = (WEB / "guide.css").read_text(encoding="utf-8")
    badge = css[css.index(".shot__badge {") : css.index("}", css.index(".shot__badge {"))]
    assert "background: var(--c-info);" in badge
    assert "width: 24px;" in badge
    assert "height: 24px;" in badge
    for alarm in ("--c-serious", "--c-reject", "--c-official", "--c-code-red"):
        assert alarm not in css, alarm


def test_the_lightbox_is_one_dialog_that_closes_on_escape_and_gives_focus_back() -> None:
    assert GUIDE.count('<dialog id="shot-box"') == 1
    assert "box.showModal();" in SHOT_JS
    assert "opener?.focus()" in SHOT_JS
    assert 'matchMedia("(prefers-reduced-motion: reduce)")' in SHOT_JS


def test_the_honesty_facts_stay_on_the_guide() -> None:
    for fact in (
        "Decision support only",
        "Ring of Fire Air (RFA) is a fictional airline",
        "Nothing is sent to an aircraft or any real system",
        "REPLAY plays recorded real feeds, or synthetic demo data where it says so",
    ):
        assert fact in GUIDE, fact
    # the long parts fold under More, each with the id the Wall links to
    for ident in ("read", "how", "about", "policy"):
        assert f'<details id="{ident}" class="gfold">' in GUIDE, ident
