"""The Guide's "Start here" (redesign D21, D22, D28): the static block first, the dedupe of the
Help-list copies, the Google Cloud sentence said once, the page shells (privacy, document) and the
tour's onboarding step (SPEC-v2 11). Source checks only; the page is drawn by the browser.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "tephra" / "web"


def _read(name: str) -> str:
    return (WEB / name).read_text(encoding="utf-8")


def _meta(head: str, attr: str, name: str) -> str | None:
    m = re.search(rf'<meta {attr}="{re.escape(name)}" content="([^"]*)">', head)
    return m.group(1) if m else None


GUIDE = _read("guide.html")
GUIDE_JS = _read("guide.js")
CONTROLS = _read("wall/controls.js")
EXPLAIN = _read("wall/explain.js")
WALL_JS = sorted((WEB / "wall").glob("*.js"))
WEB_TREE = [
    p
    for p in WEB.rglob("*")
    if p.suffix in {".html", ".js", ".css", ".json", ".md"} and p.is_file()
]


def test_the_guide_has_one_h1_and_start_here_comes_first() -> None:
    assert GUIDE.count("<h1") == 1
    assert "TEPHRA: a volcanic-ash decision desk" in GUIDE
    start = GUIDE.index('id="start"')
    # the static block, then the tour (UI-DESIGN 7.29), then Try it, then the folds guide.js fills
    tour = GUIDE.index('id="tour-wall"')
    assert start < tour < GUIDE.index('id="try"') < GUIDE.index('id="more"')
    assert GUIDE.index('href="#start">Start here') < GUIDE.index('href="#read">Map key')
    # guide.js fills Map key first, then How it works
    read = GUIDE_JS.index('getElementById("read-body")')
    assert read < GUIDE_JS.index('getElementById("how-body")')


def test_the_case_paragraph_comes_from_the_wall_s_one_source() -> None:
    assert 'import { caseStrip, loadCases, caseOf } from "./wall/case.js";' in GUIDE_JS
    assert "caseStrip(caseOf(state.replay?.case_id), { mode: state.mode })" in GUIDE_JS
    assert '<noscript><p class="muted">Open the demo for the case.</p></noscript>' in GUIDE
    # no static duplicate of the case's numbers on the Guide
    for digits in ("2,961", "341,000", "28 of Semeru"):
        assert digits not in GUIDE, digits
    # the ICAO sentence without "not the ash centre"
    assert "The operator must resolve those conflicts (ICAO Doc 9974)." in GUIDE
    assert "not the ash centre" not in GUIDE


def test_the_try_it_steps_carry_the_links() -> None:
    assert "Try it in three minutes" in GUIDE
    for href in (
        'href="/demo"',
        'href="/demo#details-disagree"',
        'href="/demo#details-estimate"',
        'href="/assistant"',
        'href="/desk"',
        'href="/demo#track-record"',
        'href="#policy"',
    ):
        assert href in GUIDE, href
    assert "<b>Open the demo</b><span>Press Start, then F to fit the volcano</span>" in GUIDE
    # the Wall moved to /demo: no link on the Guide still means it by "/"
    assert not re.search(r'href="/#', GUIDE)
    assert '"/#details-' not in GUIDE_JS
    assert 'id="try-desk"' in GUIDE
    assert GUIDE.count('<li id="try-desk">') == 1
    assert "state?.visitor_access === true" in GUIDE_JS
    assert 'text: "Enter the Desk as a visitor"' in GUIDE_JS


def test_the_assistant_sentence_is_said_once_in_the_wall_modules() -> None:
    hits = sum(_read(f"wall/{p.name}").count("reads feeds and drafts text") for p in WALL_JS)
    assert hits == 1
    # the About sentence (pinned by test_ui_ai_quiet) is the one that stays
    assert "TEPHRA Assistant is an AI assistant. It reads feeds and drafts text." in CONTROLS
    # the Help-list copies went
    assert 'el("li", { text: "TEPHRA Assistant is an AI assistant.' not in CONTROLS
    assert (
        'el("li", { text: "Nothing is sent to an aircraft or to any real system." })'
        not in CONTROLS
    )
    assert "REPLAY means the data was recorded" not in CONTROLS
    assert "TEPHRA Assistant is TEPHRA's AI assistant. It reads feeds" not in EXPLAIN


def test_never_smaller_is_said_at_most_twice_across_help_and_explain() -> None:
    phrase = "never smaller than the official area"
    assert CONTROLS.count(phrase) + EXPLAIN.count(phrase) <= 2
    assert '"TEPHRA\'s estimate", "the amber dashed line"' in CONTROLS
    assert "drawn as the amber dashed line; the official area stays binding." in EXPLAIN


def test_about_keeps_its_honesty_lines() -> None:
    assert "Decision support only. Not for operational use." in CONTROLS
    assert "Nothing is sent" in CONTROLS
    assert "Ring of Fire Air (RFA) is a fictional airline." in CONTROLS
    # the RFA subs in Help went (the glossary row and About say it)
    # (the key names the airline's code: RFA in the demo, an airline's own in its own TEPHRA)
    assert "`${code} flight in or heading in`, null" in CONTROLS
    assert "our fictional airline" not in CONTROLS


def test_runs_on_google_cloud_is_said_once_in_the_web_tree_and_stays_true_locally() -> None:
    pattern = re.compile(r"runs on Google Cloud", re.I)
    hits = {p.name: len(pattern.findall(p.read_text(encoding="utf-8"))) for p in WEB_TREE}
    assert sum(hits.values()) == 1, hits
    assert (
        "The public demo runs on Google Cloud: Cloud Run (Singapore), Cloud Scheduler, Firestore, "
        "Secret Manager, Artifact Registry; the Gemini API and the Agent Development Kit." in GUIDE
    )
    for p in WEB_TREE:
        assert "Built on" not in p.read_text(encoding="utf-8"), p.name


@pytest.mark.parametrize("page", ["guide.html", "home.html", "onboard.html", "workspace.html"])
def test_the_og_tags_match_the_wall_s(page: str) -> None:
    head = _read(page).split("</head>")[0]
    wall = _read("index.html").split("</head>")[0]
    assert _meta(head, "property", "og:type") == "website"
    title = _meta(head, "property", "og:title") or ""
    assert title == "TEPHRA" or title.startswith("TEPHRA "), title
    desc = _meta(head, "property", "og:description")
    assert desc is not None
    assert desc.startswith(_meta(wall, "property", "og:description") or "x")
    assert _meta(head, "property", "og:image") == _meta(wall, "property", "og:image")
    assert _meta(head, "property", "og:image:width") == "1200"
    assert _meta(head, "property", "og:image:height") == "630"
    assert _meta(head, "name", "twitter:card") == "summary_large_image"


def test_the_guide_description_is_the_wall_s_plus_its_role() -> None:
    wall = _meta(_read("index.html").split("</head>")[0], "name", "description")
    assert _meta(GUIDE.split("</head>")[0], "name", "description") == f"{wall} The Guide."


def test_the_keyboard_row_and_heading_say_where_they_apply() -> None:
    assert '["?", "Open the Guide"]' in CONTROLS
    assert '"This help"' not in CONTROLS
    assert 'text: "Keyboard, on the Wall"' in CONTROLS
    # on the Guide the words and the keyboard fold, one tap in
    assert 'el("details", { class: "more guide__fold" }' in CONTROLS


def test_the_glossary_no_model_row_says_it_is_not_a_fallback() -> None:
    glossary = _read("wall/glossary.js")
    assert "It is not a fallback: the live site never uses it in place of a model." in glossary
    assert "code templates write the text a model would" not in glossary


def test_the_policy_failure_says_reload() -> None:
    policy = _read("wall/policy.js")
    assert "The operator policy could not be loaded. Reload the page." in policy
    assert "try again in a moment" not in policy


def test_the_credits_carry_the_feed_content_row_and_the_licence_inventory() -> None:
    assert (
        '["Feed content", "SIGMETs, advisories and observatory notices", '
        '"Credited on each card: BMKG, Tokyo and Darwin VAAC, PVMBG; relays by NWS and IEM"]'
        in CONTROLS
    )
    assert 'href: "/static/THIRD_PARTY.md", text: "Full licence inventory"' in CONTROLS
    assert "about__attrib" not in CONTROLS
    assert (WEB / "THIRD_PARTY.md").exists()


def test_privacy_is_on_the_night_theme_with_the_shared_header_and_discloses_the_visitor_name() -> (
    None
):
    privacy = _read("privacy.html")
    assert '<meta name="color-scheme" content="dark">' in privacy
    assert '<html lang="en" data-theme="dark">' in privacy
    assert "theme-boot.js" not in privacy
    assert 'class="guidebar tn-bar"' in privacy
    assert 'class="topnav" aria-label="TEPHRA pages"' in privacy
    assert "tn-strip" not in privacy
    assert "docdisclaimer" not in privacy
    assert "Wall readers" in privacy
    assert "Wall visitors" not in privacy
    assert (
        "Nothing you do on the Wall or the Guide is sent to Gemini. If you enter the Desk as a "
        "visitor, the name you type (or the one TEPHRA gives you) is written into TEPHRA's public "
        "decision record with each decision you make; use a first name or none." in privacy
    )
    assert "github.com/officialasishkumar/tephra/issues" in privacy


def test_the_document_page_s_bar_carries_the_pill_nav() -> None:
    doc = _read("doc.html")
    assert 'href="/static/topnav.css"' in doc
    assert '<nav class="topnav" aria-label="TEPHRA pages">' in doc
    assert 'src="/static/topnav.js"' in doc
    assert '<html lang="en" data-theme="dark">' in doc
    assert '<meta name="color-scheme" content="dark">' in doc
    # the shared nav module hides Onboard by the server's feature set, as the other pages do,
    # and swaps it for Workspace when an airline is signed in
    topnav = _read("topnav.js")
    assert "applyFeatureNav()" in topnav
    assert "initAccountNav()" in topnav


def test_privacy_says_what_an_airline_account_keeps() -> None:
    privacy = _read("privacy.html")
    assert '<h2 id="accounts">Airline accounts</h2>' in privacy
    accounts = privacy[privacy.index('id="accounts"') : privacy.index("<h2>Questions</h2>")]
    for words in (
        "the password as a salted scrypt hash, never the password itself",
        "a hash of the recovery code",
        "the dispatchers' names or initials",
        "Google Cloud Firestore",
        "SQLite",
        "never public, never written into the audit trail and never sent to Gemini",
        "from sign-up on, the onboarding answers with the account",
        "answers not submitted are not shown to them",
        "goes only into the zip",
        "<code>tephra_airline</code>",
        "HttpOnly and SameSite=Strict",
        "12 hours",
        "deletes it from the workspace's account menu",
        "signing out clears them",
    ):
        assert words in accounts, words
    # the Cookies paragraph no longer says the Desk's cookie is the only one
    assert "The only cookie is" not in privacy


def test_the_guide_tour_folds_connect_into_onboarding() -> None:
    assert 'id="tour-connect"' not in GUIDE
    assert 'href="/connect"' not in GUIDE
    step = GUIDE[GUIDE.index('id="tour-onboard"') : GUIDE.index('id="try"')]
    assert 'data-feature="onboard" hidden' in step
    assert '<h2 id="tour-onboard-h" class="gstep__h">Onboard your airline</h2>' in step
    assert 'href="/onboard">Open onboarding' in step
    assert 'href="/demo?intro=0">Open the demo' in GUIDE
    run = GUIDE[GUIDE.index('id="run"') : GUIDE.index('id="more"')]
    assert 'data-feature="onboard" hidden' in run
    # the nine "what you provide" lines are said on the onboarding landing, not here
    assert "ICAO 24-bit address" not in GUIDE
    # a hidden part shows by the server's features, the nav by applyFeatureNav
    assert 'document.querySelectorAll("main [data-feature]")' in GUIDE_JS


def test_the_guide_is_light_capable_with_its_theme_control() -> None:
    head = GUIDE.split("</head>")[0]
    assert '<meta name="color-scheme" content="dark light">' in head
    assert head.index('src="/static/theme-boot.js"') < head.index('href="/static/tokens.css"')
    assert 'id="guide-theme"' in GUIDE
    assert 'getElementById("guide-theme").replaceChildren(themeControl())' in GUIDE_JS
    # the screenshots stay on the night theme
    assert GUIDE.count('<div class="shot__frame night">') == GUIDE.count('class="shot__frame')


@pytest.mark.parametrize(
    "name",
    [
        "guide.html",
        "guide.js",
        "guide.css",
        "privacy.html",
        "doc.html",
        "topnav.css",
        "topnav.js",
        "tokens.css",
        "home.html",
        "home.js",
        "home.css",
        "home-boot.js",
        "theme-boot.js",
        "theme.js",
        "account-nav.js",
        "replay-words.js",
        "five-steps.js",
        "five-steps.css",
        "welcome.css",
        "wall/welcome.js",
        "wall/features.js",
        "wall/controls.js",
        "wall/explain.js",
        "wall/glossary.js",
        "wall/policy.js",
    ],
)
def test_no_visitor_word_slip_and_no_inline_style_in_the_task_s_files(name: str) -> None:
    text = _read(name)
    assert not re.search(r"\bjudges?\b|\bjudging\b|\bjudged\b", text, re.I), name
    assert " style=" not in text, name
    # el(..., { style }) is an inline style; Intl's { style: "currency" } is not
    assert not re.search(r'el\("[a-z]+", \{[^}]*\bstyle:', text), name
