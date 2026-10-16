"""Home at ``/`` (SPEC-v2 5.1): one line on what TEPHRA is and two choices, Watch the demo first,
the onboarding parts only while the server shows them, the decision-support line in the footer,
the old ``/#...`` links sent on to the demo before anything draws, and the map a real frame of
the replay that says which. Source checks; the browser draws the page."""

import re
from pathlib import Path

from PIL import Image

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
HTML = (WEB / "home.html").read_text(encoding="utf-8")
HEAD = HTML.split("</head>")[0]
JS = (WEB / "home.js").read_text(encoding="utf-8")
CSS = (WEB / "home.css").read_text(encoding="utf-8")
BOOT = (WEB / "home-boot.js").read_text(encoding="utf-8")
MAX_IMAGE_BYTES = 150_000


def test_the_skip_link_leads_to_the_choices() -> None:
    assert '<a class="skip-link" href="#home-choices">Skip to the choices</a>' in HTML
    assert 'id="home-choices" class="home__choices" tabindex="-1"' in HTML
    assert HTML.index('class="skip-link"') < HTML.index('<header class="tn-bar')


def test_watch_the_demo_is_focused_first_and_read_with_the_line() -> None:
    demo = re.search(r"<a id=\"go-demo\"[^>]*>", HTML)
    assert demo
    tag = demo.group(0)
    assert 'href="/demo"' in tag
    assert "autofocus" in tag
    assert 'aria-describedby="home-line"' in tag
    assert 'class="go go--primary"' in tag
    assert '<h1 id="home-line" class="home__line">' in HTML
    assert "Watch the demo" in HTML
    assert HTML.count("autofocus") == 1


def test_the_onboarding_parts_wait_for_the_server_s_features() -> None:
    onboard = re.search(r"<a id=\"go-onboard\"[^>]*>", HTML)
    assert onboard
    assert 'data-feature="onboard" hidden' in onboard.group(0)
    assert '<p class="home__signin" data-feature="onboard" hidden>' in HTML
    assert 'Already onboarded? <a href="/signin">Sign in to your workspace</a>' in HTML
    assert '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>' in HTML
    assert 'document.querySelectorAll("main [data-feature]")' in JS
    # Sign in is said once: the body line carries it, the header shows nothing while signed out
    assert 'initAccountNav({ right: $("tn-right"), signin: false })' in JS
    assert '"Your airline workspace"' in JS


def test_the_footer_says_decision_support_only() -> None:
    assert (
        "Decision support only: a person approves every advisory, and nothing is sent to an "
        "aircraft." in HTML
    )
    for link in ('href="/guide"', 'href="/guide#about-credits"', 'href="/privacy"'):
        assert link in HTML.split("<footer")[1], link


def test_the_demo_tile_says_replay_and_the_fictional_airline() -> None:
    assert '"Replay"' in JS
    assert '"Ring of Fire Air, a fictional airline"' in JS
    assert 'state?.mode === "REPLAY"' in JS
    for words in (
        '"The live picture, from public feeds · no sign-in"',
        '"A replay of invented demo data · no sign-in"',
        '"No sign-in"',
    ):
        assert words in JS, words


def test_the_live_count_says_it_is_live_and_the_cap_names_the_captured_frame() -> None:
    assert '"Now in the replay"' in JS
    assert 'RFA flight${n === 1 ? "" : "s"} in or heading in' in JS
    frame = re.search(r'^const MAP_FRAME = \{ at: "(\d{2}:\d{2})", case: "([^"]+)" \};$', JS, re.M)
    assert frame, "the capture's clock is a constant beside the image"
    assert "`Map from the replay at ${MAP_FRAME.at} UTC · ${MAP_FRAME.case}`" in JS
    assert 'document.title = shown ? "REPLAY - TEPHRA" : "TEPHRA";' in JS
    assert "<title>TEPHRA</title>" in HEAD


def test_old_hash_links_go_to_the_demo_before_anything_draws() -> None:
    assert 'location.replace("/demo" + location.search + location.hash)' in BOOT
    assert "import " not in BOOT
    assert "export " not in BOOT
    boot = HEAD.index('<script src="/static/home-boot.js"></script>')
    assert boot < HEAD.index('<script src="/static/theme-boot.js"></script>')
    assert boot < HEAD.index('<script type="module"')
    assert boot < HEAD.index('<link rel="stylesheet"')


def test_no_inline_script_or_style() -> None:
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", HTML)
    assert " style=" not in HTML
    assert "<style" not in HTML
    assert "innerHTML" not in JS


def test_the_head_is_light_capable_and_carries_the_og_block() -> None:
    assert '<meta name="color-scheme" content="dark light">' in HEAD
    assert '<meta property="og:title" content="TEPHRA">' in HEAD
    assert '<meta name="robots" content="noindex, nofollow">' in HEAD
    order = [
        HEAD.index('href="/static/tokens.css"'),
        HEAD.index('href="/static/topnav.css"'),
        HEAD.index('href="/static/home.css"'),
        HEAD.index('src="/static/home.js"'),
    ]
    assert order == sorted(order)


def test_the_map_is_a_captured_frame_or_not_there() -> None:
    images = [WEB / "home" / "replay-map.webp", WEB / "home" / "replay-map-phone.webp"]
    if "<picture>" not in HTML:
        return
    assert '<div class="home__map night" aria-hidden="true">' in HTML
    for path, size in zip(images, [(1600, 1000), (780, 400)], strict=True):
        assert path.stat().st_size <= MAX_IMAGE_BYTES, path.name
        with Image.open(path) as im:
            assert im.format == "WEBP", path.name
            assert im.size == size, path.name


def test_phones_get_the_map_band_on_top_with_16_px_gutters() -> None:
    assert "@media (max-width: 760px)" in CSS
    phone = CSS[CSS.index("@media (max-width: 760px)") :]
    assert "height: 200px;" in phone
    assert "grid-template-columns: minmax(0, 1fr);" in phone
    for track in re.findall(r"grid-template-columns: ([^;]+);", CSS):
        for part in re.findall(r"minmax\([^)]*\)|\S+", track):
            assert part.startswith("minmax(0") or part.endswith("px") or part == "auto", track
