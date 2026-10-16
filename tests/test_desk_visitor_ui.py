"""The Desk's visitor path and feature gating (SPEC T11): static checks of the page sources, like
the inventory test. The sign-in card offers "Enter as a visitor" while /api/state says
visitor_access; a visitor's menu never offers the display switch; the review handles the server's
409 refusals (rule_blocked, cone_changed) with Reject as the way out; hidden features consult
has(); the assistant sheet names Cloud Run only from SystemState.cloud; the retired word for a
visitor (the export's forbidden list) is gone from the Desk sources.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
DESK_SOURCES = [
    WEB / "desk.html",
    WEB / "desk.js",
    WEB / "desk.css",
    *sorted((WEB / "desk").glob("*.js")),
]
JUDGE = re.compile(r"\bjud(?:ge|ges|ging|ged)\b", re.IGNORECASE)
# CSP forbids inline styles (SPEC rule 5): no style attribute in the page, no el(..., { style })
# in a module. Intl's `{ style: 'currency' }` is a number format option, not a style.
INLINE_STYLE_ATTR = re.compile(r"\sstyle=")
EL_STYLE = re.compile(r"\{\s*style:(?!\s*'currency')")
WHY = "Why ›"  # noqa: RUF001 (the UI's own "Why" pin, angle quote included)


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    nxt = re.search(r"\n(?:export )?(?:async )?function ", source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def test_sign_in_card_offers_enter_as_a_visitor() -> None:
    html = _read("desk.html")
    assert "Enter as a visitor" in html
    assert 'id="visitor-card"' in html
    card_tag = html.split('id="visitor-card"')[1].split(">")[0]
    assert "hidden" in card_tag  # nothing flashes before /api/state says visitor_access
    assert 'for="visitor-name"' in html
    assert "Your name (optional)" in html
    assert "Visitors cannot change the display or the feeds." in html
    assert "go into the public record as visitor:&lt;your name&gt;" in html
    # Visitor or Dispatcher: two tabs, hidden with the card until the state says visitor_access
    tabs_tag = html.split('id="login-tabs"')[1].split(">")[0]
    assert 'role="tablist"' in tabs_tag
    assert "hidden" in tabs_tag
    assert 'aria-controls="visitor-card"' in html
    assert 'aria-controls="dispatcher-card"' in html


def test_login_reads_visitor_access_and_posts_the_visitor_route() -> None:
    login = _read("desk/login.js")
    assert "app.state.visitor_access === true" in login
    assert "export function syncVisitorCard()" in login
    sync = _function(login, "syncVisitorCard")
    assert "e.tabs.hidden = !on;" in sync
    assert "way = e.name.value ? 'dispatcher' : 'visitor';" in sync
    enter = _function(login, "enterAsVisitor")
    assert "api(PATHS.visitor, { method: 'POST', body: { name: name || null } })" in enter
    assert "code === 'visitor_off'" in enter
    assert "code === 'too_many_visitors'" in enter
    assert "lock(" in enter
    assert "'Visitor access is switched off on this server.'" in login
    assert "visitor: '/api/desk/visitor'" in _read("desk/api.js")


def test_desk_imports_features_and_hides_hidden_entries() -> None:
    desk = _read("desk.js")
    assert "import { applyFeatureNav, has, setFeatures } from './wall/features.js';" in desk
    assert "setFeatures(state.features);" in _function(desk, "applyState")
    features = _function(desk, "applyFeatures")
    assert "byId('crew-report-btn').hidden = !has('crew');" in features
    assert "byId('paste-notice').hidden = !has('notices');" in features
    assert "applyFeatureNav();" in features
    assert "/connect" not in features
    assert "syncVisitorCard();" in _function(desk, "applyState")
    ask = _read("desk/ask.js")
    assert "has('voice')" in ask
    assert "composer.mic.hidden = !has('voice');" in ask
    account = _read("desk/account.js")
    assert "has('connect') && !visitor" in account
    assert "has('onboard') && !visitor" in account


def test_visitor_review_opens_at_once_and_tab_ask_routes_to_the_drawer() -> None:
    desk = _read("desk.js")
    enter = _function(desk, "enterDesk")
    assert "session.role === 'visitor' && walkOrder()[0]" in enter
    assert "selectDraft(walkOrder()[0].id, { focus: false })" in enter
    route = _function(desk, "route")
    assert "if (r.tab === 'ask') openAsk();" in route
    assert r"/^#tab\/(queue|ask|network|docs)$/" in desk


def test_a_visitor_menu_has_no_display_switch() -> None:
    account = _read("desk/account.js")
    menu = _function(account, "renderMenu")
    assert "const visitor = Boolean(me && me.role === 'visitor');" in menu
    assert "if (!visitor) {" in menu
    dispatcher_only = menu.split("if (!visitor) {")[1].split("\n  }\n")[0]
    assert "'Change display…'" in dispatcher_only
    assert "Signed in as ${me ? sessionLabel(me) : '–'}" in menu  # noqa: RUF001
    assert "Session ends ${hhmmz(me.expires_at)}" in menu
    assert "text: 'Sign out'" in menu
    # CP-06: below 600 px the menu lists the other pages
    assert "window.innerWidth < PAGES_BELOW_PX" in menu
    assert "text: 'Demo'" in menu
    assert "href: '/demo'" in menu
    assert "text: 'Guide'" in menu
    fmt = _read("desk/format.js")
    assert "`visitor:${me.name}`" in fmt


def test_review_handles_rule_blocked_and_cone_changed() -> None:
    review = _read("desk/review.js")
    decide = _function(review, "decide")
    assert "code === 'rule_blocked'" in decide
    assert "code === 'cone_changed'" in decide
    assert "sheet.ruleBlocked = (res.data && res.data.detail)" in decide
    # one reload after cone_changed, never a loop
    assert "if (!sheet.reloaded) {" in decide
    assert "app.hub.reloadDrafts();" in decide
    assert "reloadDrafts: () => loadDrafts()," in _read("desk.js")
    assert (
        "The ash area changed since this draft was written. Reject it; the flight is planned "
        "again when TEPHRA Assistant is on · " in review
    )
    bar = _function(review, "renderBar")
    assert "} else if (sheet.coneChanged) {" in bar
    cone = bar.split("} else if (sheet.coneChanged) {")[1].split("} else if")[0]
    assert "'data-go': 'reject'" in cone
    assert "data-decide" not in cone
    assert "holdButton" not in cone
    assert f"text: '{WHY}'" in cone
    assert "Refused by code: ${sheet.ruleBlocked}" in bar
    assert "Queued under ${sessionLabel(app.me) || 'your name'}" in bar


def test_visitor_empty_state_only_when_nothing_waits_by_hand() -> None:
    queue = _read("desk/queue.js")
    branch = queue.split("app.me.role === 'visitor') {")[0].rsplit("} else if", 1)[1]
    assert "n === 0 && !openFailures().length && app.me &&" in branch
    assert "Nothing waits for you right now." in queue
    assert (
        "The replay plays on; drafts come when a flight approaches the ash and TEPHRA "
        "Assistant is on · " in queue
    )
    assert f"text: '{WHY}'" in queue
    assert "text: 'See the demo'" in queue
    # the hand branch (H9) stays for every role
    assert "hand ? 'No drafts to approve.' : 'Nothing waits for you.'" in queue


def test_assistant_sheet_runs_on_line_only_on_cloud_run() -> None:
    budget = _read("desk/budget.js")
    runs = _function(budget, "runsOn")
    assert "c.platform !== 'cloud-run'" in runs
    assert "`Runs on Cloud Run${where}${rev}`" in runs
    assert "revision" in runs
    assert "runsOn()" in _function(budget, "openBudget")


def test_desk_og_tags_and_description() -> None:
    html = _read("desk.html")
    assert '<meta property="og:title" content="TEPHRA Desk">' in html
    shared = (
        "When official ash reports disagree, TEPHRA keeps the wider estimate, finds the "
        "flights heading in and drafts the advisory a dispatcher approves. Replay demo · "
        "fictional airline · decision support only."
    )
    assert shared in _read("index.html")
    tail = f"{shared} The Desk, where a person decides."
    assert f'<meta property="og:description" content="{tail}">' in html
    assert f'<meta name="description" content="{tail}">' in html
    assert '<meta property="og:image" content="https://' in html


def test_no_judge_word_and_no_inline_style_in_the_desk_sources() -> None:
    for path in DESK_SOURCES:
        text = path.read_text(encoding="utf-8")
        assert not JUDGE.search(text), path.name
        if path.suffix == ".html":
            assert not INLINE_STYLE_ATTR.search(text), path.name
        elif path.suffix == ".js":
            assert not EL_STYLE.search(text), path.name
