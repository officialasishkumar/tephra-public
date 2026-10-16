"""Static checks of the onboarding, sign-in and workspace pages (SPEC-v2 §6, §7): the shared nav
with Onboard current, the landmarks every page needs, no inline script or style (CSP), text only
through textContent, one file that touches the browser's storage, a Gemini key that has no field
name and reaches no request, the honesty labels these pages say, and the account first: sign-up
on the landing, answers saved to the account, Review submits, the kit only once submitted.
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
    WEB / "desk" / "airlines.js",
    WEB / "desk" / "connections.js",
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
        assert "Decision support only" in html, page


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


def test_the_gemini_key_has_no_name_and_reaches_no_request() -> None:
    kit = _read("workspace/kit.js")
    field = kit.split("function keyInput()")[1].split("\n}\n")[0]
    assert 'type: "password"' in field
    assert 'autocomplete: "off"' in field
    assert "name:" not in field
    assert '"pagehide"' in field
    assert "kit-gemini-key" not in _read("workspace/overview.js")
    assert "keyField" not in _read("workspace/overview.js")
    for rel in ("onboard/draft.js", "workspace/api.js", "onboard/pages.js"):
        text = _read(rel)
        assert "geminiKey" not in text, rel
        assert "gemini_key" not in text, rel
    for path in SOURCES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "call(" in line or "fetch(" in line:
                assert "geminiKey" not in line, (path.name, line)
                assert "gemini_key" not in line, (path.name, line)
    assert "It goes only into the zip made in this tab. TEPHRA never receives or stores it." in kit


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
        "Password reset by email is not built",
        "private to your account",
        "may be used to improve Google's products",
    ):
        assert label in text, label
    code = _read("onboard.js")
    provide = code.split("function provideList()")[1].split("\nfunction ")[0]
    assert "How to onboard: what you provide" in provide
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert 'el("b", { text: "Not built yet. " }), NOT_BUILT' in landing
    assert 'el("b", { text: "Not built yet. " }), NOT_BUILT' in _read("workspace/overview.js")
    assert (
        'export const NOT_BUILT = "This shared site runs the demo only. To check your own flights, '
        'run your own TEPHRA with the setup kit.";' in _read("onboard/pages.js")
    )
    assert "Running your live operation on this shared TEPHRA" not in text
    # own flight numbers work in an airline's own TEPHRA (OWNFLIGHTS, 16 Oct 2026): no page says
    # its drafts use Ring of Fire Air numbers any more
    assert "Ring of Fire Air number" not in text
    assert "RFA number" not in text


def test_the_landing_says_who_reads_the_answers_once() -> None:
    """The Desk's review list shows every submitted answer to this site's dispatchers: the
    sign-up card says so once and never claims nothing reaches the Desk."""
    card = _read("onboard.js").split("function signupCard()")[1].split("\nfunction ")[0]
    assert "this site's TEPHRA dispatchers, who verify your airline, read your answers" in card
    assert "reaches the demo, the map or the Desk" not in card
    assert _read("onboard.js").count("the Desk's picture") == 1


def test_the_account_comes_first_and_no_answer_is_kept_in_the_browser() -> None:
    """The owner (16 Oct 2026): "whats the need of writing this, first sign up"."""
    code = _read("onboard.js")
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert landing.index("side,") < landing.index("provideList()")
    card = code.split("function signupCard()")[1].split("\nfunction ")[0]
    assert '"Create account"' in card
    assert '"Already have an account? "' in card
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
    assert '"Back and Next save your answers to your account."' in code
    privacy = _read("privacy.html")
    assert "from sign-up on, the onboarding answers with the account" in privacy


def test_a_signed_in_airline_is_sent_to_its_workspace_not_a_second_account() -> None:
    code = _read("onboard.js")
    landing = code.split("function landing()")[1].split("\nfunction ")[0]
    assert "S.account?.signedIn" in landing
    assert '"Open your workspace"' in landing
    assert "You are signed in as" in landing
    render = code.split("async function render(")[1].split("\n}\n")[0]
    assert "S.account = await initAccountNav(" in render
    assert 'location.replace("/workspace/answers")' in render
    # a draft resumes at its first unfinished page; signed out, the pages go to the landing
    assert "firstUnfinished(S.draft, ctxFor)" in render
    assert 'redirect("/onboard"' in render
    assert 'res.data?.status === "draft" && !next ? "/onboard"' in _read("workspace/signin.js")


def test_a_drafts_workspace_continues_onboarding_and_has_no_kit_yet() -> None:
    overview = _read("workspace/overview.js")
    body = overview.split("export function renderOverview(main, view) {")[1]
    assert body.index('if (view.status === "draft")') < body.index("kitCard(view)")
    assert "Continue onboarding · step ${page.n} of 9" in overview
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
