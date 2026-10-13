"""The Desk redesign (docs/UI-DESIGN.md 10.17): a static check of the page sources, like the
inventory test. Decide is sorted by the act-by time code computes, the tabs are a real tablist
in the order Decide, Airports, Paperwork, Ask, one number counts what waits, Reject is never red,
a decision leaves a receipt line instead of a toast, and the review's facts and pages exist.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
DESK_FILES = [WEB / "desk.html", WEB / "desk.js", *sorted((WEB / "desk").glob("*.js"))]
COMMENT = re.compile(r"^\s*(//|/\*|\*|<!--)")


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    nxt = re.search(r"\n(?:export )?(?:async )?function ", source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def _code_lines() -> list[tuple[str, str]]:
    out = []
    for path in DESK_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not COMMENT.match(line):
                out.append((path.name, line))
    return out


def test_decide_sorts_by_act_by_not_inside_first() -> None:
    fmt = _read("desk/format.js")
    assert "export function byActBy(" in fmt
    assert "export const byUrgency = byActBy;" in fmt
    assert "Number(b.inside_now) - Number(a.inside_now)" not in fmt
    act = _function(fmt, "actBy")
    # heading in: the entry; inside with a change: act now; keep watching or continue: no clock
    assert "if (watchOnly(adv)) return null;" in act
    assert "entryAt(adv)" in act
    assert "adv.action === 'MONITOR' || adv.action === 'CONTINUE'" in fmt
    queue = _read("desk/queue.js")
    assert "draftList().sort(byActBy)" in queue
    assert "byUrgency" not in queue
    assert "byUrgency" not in _read("desk.js")


def test_decide_groups_and_lead_card() -> None:
    queue = _read("desk/queue.js")
    for words in ("'Before entry'", "'Keep watching'", "'Other decisions'", "'Review one by one'"):
        assert words in queue, words
    assert "function buildLead(" in queue
    # the lead never swaps under the thumb: a more urgent item is a line with "Show"
    assert "More urgent: " in queue
    html = _read("desk.html")
    for ident in ("watch-section", "other-section", "q-receipt"):
        assert f'id="{ident}"' in html, ident
    # Plan by hand is group 1, right after the lead card
    assert html.index('id="q-next"') < html.index('id="fail-section"') < html.index('id="cards"')


def test_one_waiting_count_for_title_badge_and_heading() -> None:
    desk = _read("desk.js")
    assert "export function waitingCount(" in _read("desk/queue.js")
    assert "const n = app.me ? waitingCount().n : 0;" in desk
    assert "setBadges({ queue: waitingCount().n }" in desk
    assert "${c.n} waiting" in _read("desk/queue.js")
    # only Decide has a badge
    tabs = _read("desk/tabs.js")
    assert "name === 'queue' ? el('span', { class: 'tab__badge'" in tabs


def test_tabs_are_a_real_tablist_in_the_new_order() -> None:
    tabs = _read("desk/tabs.js")
    assert "export const TABS = ['queue', 'network', 'docs', 'ask'];" in tabs
    assert "setAttribute('role', 'tablist')" in tabs
    assert "role: 'tab'" in tabs
    assert "'aria-selected'" in tabs
    assert "setAttribute('role', 'tabpanel')" in tabs
    assert "aria-current" not in tabs


def test_reject_is_never_red() -> None:
    review = _read("desk/review.js")
    assert "btn--reject" not in review
    css = _read("desk.css")
    last = css[css.rindex(".btn--reject {") :]
    rule = last[: last.index("}")]
    assert "--c-reject" not in rule
    solid = css[css.rindex(".btn--reject-solid {") :]
    assert "--c-reject" not in solid[: solid.index("}")]


def test_the_receipt_line_replaces_the_decision_toast() -> None:
    desk = _read("desk.js")
    assert "decisionToast" not in desk
    assert "DECISION_TOAST_MS" not in desk
    assert "setReceipt(decided);" in desk
    review = _read("desk/review.js")
    assert "id: 'receipt'" in review
    assert "'Draft crew briefing'" in review
    # the audit line only from /api/audit; nothing in its place while it is not listed
    audit = _function(review, "toggleAudit")
    assert "PATHS.audit(" in audit
    assert "Audit line not listed yet. It appears in Record when the server lists it." in audit


def test_nothing_is_sent_is_said_twice_per_approval() -> None:
    """The confirm step and the stamp; the hint under the button no longer repeats it."""
    review = _read("desk/review.js")
    assert "nothing is sent to an aircraft." in review
    assert "queued, not sent to any aircraft" in review
    assert "QUEUE_SENTENCE" not in review
    assert "'Hold to approve, or tap to confirm.'" in review


def test_review_reads_top_to_bottom_with_pages() -> None:
    review = _read("desk/review.js")
    assert "'Check before you approve'" in review
    assert "'Text to approve'" in review
    for page in ("sources", "area", "route", "record"):
        assert f"{page}: " in review[review.index("const PAGES") :][:200], page
    assert "' · ids, policy, history, audit'" in review
    assert "'Skip for now'" in review
    # REPLAY is said by the frame strip; the review adds no REPLAY note of its own
    assert "Drafted from recorded feeds" not in review
    assert "replayChip" not in review
    # HYPOTHESIS: only Keep watching or Hold
    assert "only Keep watching or Hold can be approved for this flight" in review
    assert "['MONITOR', 'HOLD'].includes(adv.action)" in review


def test_unchanged_edit_is_said_only_after_an_attempt() -> None:
    review = _read("desk/review.js")
    body = _function(review, "editProblem")
    assert "tried ?" in body
    assert "editTried = true" in review


def test_never_on_screen_words_are_gone() -> None:
    for name, line in _code_lines():
        assert "already clear" not in line, (name, line)
        assert "The model wrote the words" not in line, (name, line)
        assert "Refresh the lists" not in line, (name, line)
        assert "Decided while this page was open" not in line, (name, line)


# "AI" stays only where disclosure needs it (the About line, the free AI quota) and in the raw
# machine reason the server writes ("AI UNAVAILABLE: …", one tap in, under Technical detail).
AI_ALLOWED = (
    "TEPHRA Assistant is an AI assistant.",
    "free AI quota",
    "AI UNAVAILABLE",
)


def test_ai_is_said_only_in_the_allowed_places() -> None:
    for name, line in _code_lines():
        rest = line
        for allowed in AI_ALLOWED:
            rest = rest.replace(allowed, "")
        rest = re.sub(r"docs/UI-AI-QUIET\.md", "", rest)
        assert not re.search(r"\bAI\b", rest), (name, line.strip()[:120])


def test_ask_answer_lands_above_the_composer_and_is_announced() -> None:
    ask = _read("desk/ask.js")
    assert "sugg, log, form);" in ask
    assert "log.append(" in ask
    assert "log.prepend(" not in ask
    assert "announce(`Answer: " in ask
    assert "'aria-live': 'off'" in ask


def test_the_offline_line_is_out_of_the_header() -> None:
    html = _read("desk.html")
    head = html[html.index('<header id="dhead"') : html.index("</header>")]
    assert 'id="net-banner"' not in head
    assert 'id="net-banner"' in html[html.index('<main id="main"') :]
