"""Static checks of the onboarding, sign-in and workspace pages (SPEC-v2 §6, §7): the shared nav
with Onboard current, the landmarks every page needs, no inline script or style (CSP), text only
through textContent, one file that touches the browser's storage, a Gemini key that has no field
name and reaches no request, the honesty labels these pages say, and the account first: sign-up
on the landing, answers saved to the account, Review submits, the workspace once submitted.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
PAGES = ("onboard.html", "workspace.html")
NAV = (
    '<nav class="topnav" aria-label="TEPHRA pages"><a href="/demo">Demo</a><a href="/desk">Desk</a>'
    '<a href="/onboard" data-feature="onboard" aria-current="page">Onboard</a>'
    '<a href="/guide">Guide</a></nav>'
)
SOURCES = [
    WEB / "onboard.js",
    WEB / "workspace.js",
    *sorted((WEB / "onboard").glob("*.js")),
    *sorted((WEB / "workspace").glob("*.js")),
    WEB / "desk" / "connections.js",
    WEB / "dryrun.js",
]
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.I)
INLINE_STYLE = re.compile(r"\sstyle=|<style", re.I)
EL_STYLE = re.compile(r"\{\s*style:")
FORBIDDEN = re.compile(r"\b(judg\w*|hack\dskill)\b|@gmail\.com", re.I)


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _all() -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in SOURCES)


def test_pages_have_the_nav_skip_link_announcer_and_no_inline_code() -> None:
    for page in PAGES:
        html = _read(page)
        assert NAV in html, page
        assert '<a class="skip-link" href="#main">' in html, page
        assert 'id="announcer"' in html, page
        assert 'aria-live="polite"' in html, page
        assert 'id="main"' in html, page
        assert 'id="tn-right"' in html, page
        assert '<meta name="color-scheme" content="dark light">' in html, page
        assert html.index('src="/static/theme-boot.js"') < html.index('type="module"'), page
        assert not INLINE_SCRIPT.search(html), page
        assert not INLINE_STYLE.search(html), page
        # the footer no longer says it (owner, 17 Oct 2026: "don't put this everywhere"); the
        # sign-up tick's (i) does (tests/test_footer_said_once.py)
        assert "pfoot__honest" not in html, page


def test_no_inner_html_and_no_style_attribute_in_the_page_code() -> None:
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        assert "innerHTML" not in text, path.name
        assert "insertAdjacentHTML" not in text, path.name
        assert not EL_STYLE.search(text), path.name
        assert ".style." not in text, path.name


def test_draft_js_is_the_only_onboarding_file_using_storage() -> None:
    draft = _read("onboard/draft.js")
    for path in SOURCES:
        if path.name == "draft.js":
            continue
        assert "localStorage" not in path.read_text(encoding="utf-8"), path.name
    lines = draft.splitlines()
    uses = [i for i, line in enumerate(lines) if "localStorage." in line]
    assert uses
    for i in uses:
        above = "\n".join(lines[max(0, i - 3) : i])
        assert "try {" in above, lines[i]
    assert "export function clearOnboardStorage()" in draft
    assert "clearOnboardStorage" in _read("account-nav.js")
    assert 'from "./onboard/draft.js"' in _read("account-nav.js")


def test_no_gemini_key_is_asked_for_or_sent() -> None:
    """With the setup kit gone (owner, 17 Oct 2026: "drop it") no page asks for a Gemini key:
    only the provider and the model names are stored."""
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        for word in ("geminiKey", "gemini_key", "kit-gemini-key", "GEMINI_API_KEY"):
            assert word not in text, (path.name, word)
    assert "this site never stores it" in _read("workspace/assistant.js")


def test_the_progress_bar_is_hidden_from_screen_readers() -> None:
    html = _read("onboard.html")
    bar = html.split('id="ob-progress"')[1].split(">")[0]
    assert 'aria-hidden="true"' in bar
    assert 'role="progressbar"' not in html
    assert 'id="ob-saved" class="ob__saved" role="status"' in html


def test_the_honesty_labels_these_pages_say() -> None:
    text = _all()
    for label in (
        "ILLUSTRATIVE",
        "Not built",
        "NO MODEL",
        "DRY RUN · NOTHING TAKEN IN",
        "Pending verification",
        "is not built",
        "nothing is sent to an aircraft",
        "Email reset is not built",
        "Email reset: not built",
        "Private to your airline",
        "Running your airline on this site is not switched on yet.",
        "may be used to improve Google's products",
    ):
        assert label in text, label
    code = _read("onboard.js")
    provide = code.split("function provideList()")[1].split("\nfunction ")[0]
    assert 'el("details", { id: "ob-provide"' in provide  # closed until asked for
    assert '"What you will provide"' in provide
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert 'siteLine(has("hosted"))' in landing
    assert "notYet(view)" in _read("workspace/overview.js")
    assert "Running your live operation on this shared TEPHRA" not in text
    # own flight numbers work in an airline's own TEPHRA (OWNFLIGHTS, 16 Oct 2026): no page says
    # its drafts use Ring of Fire Air numbers any more
    assert "Ring of Fire Air number" not in text
    assert "RFA number" not in text


def test_the_landing_says_who_reads_the_answers_once() -> None:
    """TEPHRA staff's review on /admin shows every submitted answer (owner, 17 Oct 2026: staff
    verify, not the Desk): the sign-up card says so once and never claims nothing reaches the
    Desk."""
    card = _read("onboard.js").split("function signupCard()")[1].split("\nfunction ")[0]
    assert "text: WHO_READS" in card
    pages = _read("onboard/pages.js")
    assert "Only you and TEPHRA staff, who verify your airline, read your answers" in pages
    assert "TEPHRA dispatcher" not in pages
    assert "reaches the demo, the map or the Desk" not in pages + card
    assert pages.count("the Desk's picture") == 1
    # the workspace header says the same line, with the same (i)
    assert "text: WHO_READS" in _read("workspace.js")
    assert "Private to your account" not in _read("workspace.js")


def test_the_account_comes_first_and_no_answer_is_kept_in_the_browser() -> None:
    """The owner (16 Oct 2026): "whats the need of writing this, first sign up"."""
    code = _read("onboard.js")
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert landing.index("side,") < landing.index("provideList()")
    card = code.split("function signupCard()")[1].split("\nfunction ")[0]
    assert '"Create account"' in card
    assert '"Have an account? "' in card
    assert '"Work email"' in _read("onboard/review.js")
    assert '"Submit for verification"' in code
    assert "Create account and submit" not in code
    for gone in (
        "Nine short pages",
        "saved in this browser",
        "Saved in this browser",
        "Clear my answers",
        "Answers stay in this browser",
    ):
        for path in [*SOURCES, WEB / "privacy.html"]:
            assert gone.lower() not in path.read_text(encoding="utf-8").lower(), (gone, path.name)
    # every page saves to the account on Next and Back, with the small Saved mark
    assert "PATHS.draft" in code
    assert 'text: "Saved"' in code
    assert "What you typed stays on this page." in code
    assert "Back and Next save your answers to your account." not in code  # the Saved mark says it
    privacy = _read("privacy.html")
    assert "from sign-up on, the onboarding answers with the account" in privacy


def test_a_signed_in_airline_is_sent_to_its_workspace_not_a_second_account() -> None:
    code = _read("onboard.js")
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert "S.account?.signedIn" in landing
    assert '"Open Your airline"' in landing
    assert "Signed in as " in landing
    render = code.split("async function render(")[1].split("\n}\n")[0]
    assert "S.account = await initAccountNav(" in render
    assert 'location.replace("/workspace/answers")' in render
    # a draft resumes at its first unfinished page; signed out, the pages go to the landing
    assert "firstUnfinished(S.draft, ctxFor)" in render
    assert 'redirect("/onboard"' in render
    assert 'res.data?.status === "draft" && !next ? "/onboard"' in _read("workspace/signin.js")


def test_a_drafts_workspace_continues_onboarding() -> None:
    overview = _read("workspace/overview.js")
    body = overview.split("export function renderOverview(main, view) {")[1]
    assert body.index('if (view.status === "draft")') < body.index("verification(view")
    assert "Step ${page.n} of 9" in overview
    workspace = _read("workspace.js")
    assert 'view.status === "draft" ? SECTIONS.slice(0, 1) : SECTIONS' in workspace
    assert 'if (view.status === "draft" && section)' in workspace


def test_no_forbidden_words_and_no_retired_connect_page() -> None:
    for path in [*SOURCES, WEB / "onboard.html", WEB / "workspace.html", WEB / "product.css"]:
        assert not FORBIDDEN.search(path.read_text(encoding="utf-8")), path.name
    for path in [WEB / "onboard.html", WEB / "workspace.html", WEB / "desk.html"]:
        assert 'href="/connect"' not in path.read_text(encoding="utf-8"), path.name


def test_product_css_keeps_the_phone_rules() -> None:
    css = _read("product.css")
    assert "@media (max-width: 760px)" in css
    assert "@media (max-width: 900px)" in css
    assert "overflow-x: hidden" in css
    assert "white-space: nowrap" in css.split(".stamp {")[1].split("}")[0]
    assert "scroll-padding-bottom" in css
    # every grid track that could hold text is bounded, so 390 px never scrolls sideways
    tracks = re.findall(r"grid-template-columns:\s*([^;]+);", css)
    for t in tracks:
        assert "1fr" not in t or "minmax(0" in t or t.strip() in {"1fr"}, t


def test_review_problems_on_the_page_link_to_their_fields() -> None:
    code = _read("onboard.js")
    link = code.split("function problemLink(p)")[1].split("\nfunction ")[0]
    assert "href: `#${p.id}`" in link
    assert "e.preventDefault()" in link  # a hash change would re-render the page
    assert "getElementById(p.id)?.focus()" in link


def test_the_fleet_table_says_which_columns_are_optional_and_no_repo_paths() -> None:
    code = _read("onboard.js")
    assert '["home_base", "Home base", { mono: true, maxlength: 4 }, true, true]' in code
    assert '["hex", "Hex address", { mono: true, maxlength: 8 }, false, true]' in code
    assert 'optional ? el("span", { class: "opt", text: OPTIONAL })' in code
    assert (
        "text-transform: uppercase"
        not in _read("product.css").split(".ftable th {")[1].split("}")[0]
    )
    for name in ("onboard.js", "workspace.js"):
        assert "data/rfa" not in _read(name), name
