"""Home at ``/`` (SPEC-v2 5.1): one line on what TEPHRA is and two choices, Watch the demo first,
the onboarding parts only while the server shows them, Sign in in the top bar, a footer of links
with no decision-support sentence (owner, 17 Oct 2026: "don't put this everywhere"), the old
``/#...`` links sent on to the demo before anything draws, and a sky and a picture of the five
steps that carry no data (owner, 17 Oct 2026: the replay map "looks repetitve to the map").
Source checks; the browser draws the page."""

import re
from pathlib import Path

from PIL import Image

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
HTML = (WEB / "home.html").read_text(encoding="utf-8")
HEAD = HTML.split("</head>")[0]
JS = (WEB / "home.js").read_text(encoding="utf-8")
CSS = (WEB / "home.css").read_text(encoding="utf-8")
BOOT = (WEB / "home-boot.js").read_text(encoding="utf-8")
HOW = (WEB / "home" / "how.js").read_text(encoding="utf-8")
ASH = (WEB / "home" / "ash.js").read_text(encoding="utf-8")
STEPS = (WEB / "five-steps.js").read_text(encoding="utf-8")
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
    assert '<a href="/onboard" data-feature="onboard" hidden>Onboard</a>' in HTML
    assert 'document.querySelectorAll("main [data-feature]")' in JS
    # Sign in is said once, in the top bar (TEXT-SPEC H5): no body line, and only while the server
    # shows onboarding (account-nav.js adds it only when accounts are on)
    for gone in ("home__signin", "Already onboarded?", "Sign in to your workspace"):
        assert gone not in HTML, gone
        assert gone not in JS, gone
        assert gone not in CSS, gone
    assert 'initAccountNav({ right: $("tn-right"), signin: has("onboard") })' in JS
    assert '<div id="tn-right" class="tn-right"></div>' in HTML
    assert '"Your airline workspace"' in JS


def test_the_footer_is_links_only_and_the_line_says_a_dispatcher_approves() -> None:
    """Owner, 17 Oct 2026, on the footer sentence: "don't put this everywhere". The headline
    says "a dispatcher approves"; the demo's welcome dialog and About say the rest."""
    foot = HTML.split("<footer")[1]
    for gone in (
        "Decision support",
        "decision support",
        "nothing is sent",
        "home__honest",
        "i-hand",
    ):
        assert gone not in foot, gone
        assert gone not in CSS, gone
    for link in ('href="/guide"', 'href="/guide#about-credits"', 'href="/privacy"'):
        assert link in foot, link
    assert "<em>a dispatcher approves</em>" in HTML
    # the eyebrow went (TEXT-SPEC H1); the brand tick stands over the line instead
    assert "home__eyebrow" not in HTML
    assert "home__eyebrow" not in CSS
    assert ".home__copy::before" in CSS
    # the footer's Guide link shows only below 1100 px, where the top bar hides the nav
    assert '<a class="home__guide" href="/guide">Guide</a>' in HTML
    assert (
        "@media (min-width: 1100px) { .home .home__links .home__guide { display: none; } }" in CSS
    )


def test_the_two_choices_are_titles_only() -> None:
    """Owner, 16 Oct 2026: "no need to mention it here". The demo labels its own replay; the
    onboarding pages say how long they are."""
    choices = HTML[
        HTML.index('<div id="home-choices"') : HTML.index(
            "</div>", HTML.index('<div id="home-choices"')
        )
    ]
    assert choices.count('class="go__t"') == 2
    for gone in ("go__s", "go__pill", "no sign-in", "Ring of Fire Air", "Nine short pages"):
        assert gone not in choices, gone
        assert gone not in JS, gone
    assert "go__pill" not in CSS
    assert "go__s " not in CSS
    assert "replay-words" not in JS
    assert "replay-words" not in HEAD


def test_home_shows_no_replay_data() -> None:
    """The map frame, its live count and its caption are gone, and the fetch only reads the
    features: nothing on Home is a number from the replay."""
    for gone in (
        "Now in the replay",
        "exposed_count",
        "MAP_FRAME",
        "Map from the replay",
        "replay-map",
        "home-count",
        "home-cap",
        "home__map",
        "REPLAY - TEPHRA",
    ):
        for name, text in (("home.html", HTML), ("home.js", JS), ("home.css", CSS)):
            assert gone not in text, (gone, name)
    assert "<picture" not in HTML
    assert "<img" not in HTML
    assert "OpenFreeMap" not in HTML
    assert "<title>TEPHRA</title>" in HEAD
    assert "document.title" not in JS
    assert "fetch(" not in HOW
    assert "fetch(" not in ASH


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


def test_the_picture_draws_the_five_steps_from_their_one_source() -> None:
    assert 'import { FIVE_STEPS } from "../five-steps.js";' in HOW
    assert 'import { stepsList } from "./five-steps.js";' in JS
    assert 'import { howPicture } from "./home/how.js";' in JS
    assert '$("home-strip").replaceChildren(stepsList({ size: "sm" }));' in JS
    assert '<div id="home-how" class="home__how"></div>' in HTML
    assert '<div id="home-strip" class="home__strip"></div>' in HTML
    assert 'href="/static/five-steps.css"' in HEAD
    steps = re.findall(r'icon: "([\w-]+)", name: "([^"]+)", short: "([^"]+)"', STEPS)
    assert len(steps) == 5
    for icon, name, short in steps:
        for text in (icon, f'"{name}"', f'"{short}"'):
            for where, source in (("how.js", HOW), ("home.js", JS), ("home.html", HTML)):
                assert text not in source, (text, where)


def test_the_picture_is_one_labelled_image_with_nothing_focusable() -> None:
    assert 'host.setAttribute("role", "img");' in HOW
    assert 'host.setAttribute("aria-label", label());' in HOW
    assert "The advisory card is an example, not real data." in HOW
    assert '"aria-hidden": "true", focusable: "false"' in HOW
    for control in ('el("a"', 'el("button"', "tabindex", "href", "addEventListener", "innerHTML"):
        assert control not in HOW, control
    rule = CSS[CSS.index(".home__how {") : CSS.index("}", CSS.index(".home__how {"))]
    assert "pointer-events: none;" in rule
    assert "user-select: none;" in rule


def test_the_card_says_example_and_names_no_flight() -> None:
    assert 'el("span", { class: "how__tag", text: "Example" })' in HOW
    assert 'el("span", { text: "Approve" })' in HOW
    words = re.findall(r'text: "([^"]+)"', HOW)
    assert words == ["Example", "Approve"], words
    assert "RFA" not in HOW
    assert not re.search(r"\b[A-Z]{2,3}-?\d{2,4}\b", HOW)


def test_nothing_moves_under_reduced_motion_or_in_a_hidden_tab() -> None:
    reduced = CSS[CSS.index("@media (prefers-reduced-motion: reduce)") :]
    reduced = reduced[: reduced.index("\n}\n")]
    assert ".how__pulse { display: none; }" in reduced
    assert (
        ".how__ring::after, .how__approve::after, .home__strip .steps5__node::after "
        "{ animation: none; }" in reduced
    )
    assert (
        ".home.is-paused *, .home.is-paused *::after { animation-play-state: paused !important; }"
        in CSS
    )
    assert 'document.body.classList.toggle("is-paused", document.hidden)' in JS
    # the ash: one still frame under reduced motion, no frames while hidden
    assert 'window.matchMedia("(prefers-reduced-motion: reduce)")' in ASH
    assert "if (still.matches || document.hidden) return draw();" in ASH
    assert 'document.addEventListener("visibilitychange", play);' in ASH
    assert 'still.addEventListener("change", play);' in ASH


def test_the_sky_is_tokens_and_local_only() -> None:
    sky = CSS[CSS.index(".home__sky {") : CSS.index("}", CSS.index(".home__sky {"))]
    assert "#" not in sky, "the sky's colours come from tokens.css"
    assert (
        '<div class="home__sky" aria-hidden="true">'
        '<canvas id="home-ash" class="home__ash"></canvas></div>' in HTML
    )
    assert 'getPropertyValue("--home-ash")' in ASH
    for text in (HTML, CSS, HOW, ASH):
        assert "url(http" not in text
        assert "https://" not in text.replace(
            "https://tephra-647733667799.asia-southeast1.run.app/static/og.png", ""
        )


def test_the_sign_in_backdrop_keeps_its_captured_frame() -> None:
    """The replay map left Home; product.css still puts the frame behind sign-in, so the capture
    script writes that one picture and no longer touches home.js."""
    product = (WEB / "product.css").read_text(encoding="utf-8")
    assert 'url("/static/home/replay-map.webp")' in product
    assert not (WEB / "home" / "replay-map-phone.webp").exists()
    path = WEB / "home" / "replay-map.webp"
    assert path.stat().st_size <= MAX_IMAGE_BYTES
    with Image.open(path) as im:
        assert im.format == "WEBP"
        assert im.size == (1600, 1000)
    script = (WEB.parents[1] / "scripts" / "capture_signin_backdrop.mjs").read_text(
        encoding="utf-8"
    )
    assert "home.js" not in script
    assert "replay-map-phone" not in script


def test_narrow_screens_get_the_strip_with_16_px_gutters() -> None:
    narrow = CSS[CSS.index("@media (max-width: 1023px)") :]
    narrow = narrow[: narrow.index("\n}\n")]
    assert ".home__how { display: none; }" in narrow
    assert ".home__strip { display: block; max-width: 480px; }" in narrow
    assert "grid-template-columns: minmax(0, 1fr);" in narrow
    assert "@media (max-width: 760px)" in CSS
    for track in re.findall(r"grid-template-columns: ([^;]+);", CSS):
        for part in re.findall(r"minmax\([^)]*\)|\S+", track):
            assert part.startswith("minmax(0") or part.endswith("px") or part == "auto", track
