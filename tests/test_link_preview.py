"""The link preview (redesign A15): the Wall's og tags, the hand-drawn og.svg with no external
reference, the rendered og.png under the budget, and the offline script that makes it.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
HEAD = INDEX[: INDEX.index("</head>")]


def _meta(attr: str, name: str) -> str | None:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', HEAD)
    return m.group(1) if m else None


def test_the_wall_carries_the_og_tags() -> None:
    assert _meta("property", "og:type") == "website"
    assert _meta("property", "og:title") == "TEPHRA · volcanic-ash decision desk"
    desc = _meta("property", "og:description")
    assert desc is not None
    assert desc.startswith("When official ash reports disagree, TEPHRA keeps the wider estimate")
    assert desc.endswith("Replay demo · fictional airline · decision support only.")
    assert "cautious" not in desc
    image = _meta("property", "og:image")
    assert image is not None
    assert image.startswith("https://")
    assert image.endswith("/static/og.png")
    assert _meta("property", "og:image:width") == "1200"
    assert _meta("property", "og:image:height") == "630"
    assert _meta("name", "twitter:card") == "summary_large_image"


def test_the_description_says_what_gemini_does_and_what_code_keeps() -> None:
    desc = _meta("name", "description")
    assert desc is not None
    assert "Gemini proposes TEPHRA's estimate" in desc
    assert "code keeps it never smaller than the official area" in desc
    assert "a dispatcher approves every per-flight advisory" in desc
    assert desc.endswith("Decision support only; fictional airline; not for operational use.")


def test_noindex_and_robots_are_untouched() -> None:
    assert '<meta name="robots" content="noindex, nofollow">' in HEAD


def test_the_png_exists_under_the_budget() -> None:
    png = WEB / "og.png"
    assert png.exists()
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(data) < 200 * 1024
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    assert (width, height) == (1200, 630)


def test_the_svg_is_hand_drawn_with_no_external_reference() -> None:
    svg = (WEB / "og.svg").read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<svg")
    assert 'width="1200" height="630"' in svg
    assert "http://" not in svg.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "https://" not in svg
    for ref in ("<image", "data:", "@import"):
        assert ref not in svg, ref
    assert "Replay demo · fictional airline" in svg
    for word in ("TEPHRA", "Volcanic-ash decision desk", "for airline dispatch"):
        assert word in svg, word


def test_the_script_renders_offline() -> None:
    script = (ROOT / "scripts" / "make_og.sh").read_text(encoding="utf-8")
    assert script.startswith("#!/usr/bin/env bash")
    for tool in ("resvg", "rsvg-convert", "magick"):
        assert tool in script, tool
    assert "curl" not in script
    assert "http" not in script
    assert "153600" in script
