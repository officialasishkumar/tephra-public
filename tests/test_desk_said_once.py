"""The Desk says the assistant's state once (owner, 17 Oct 2026: "don't say no model everywhere";
lead decisions A, D and K3): one status in the header, only when the assistant is not on, with an
(i) for the why; REPLAY and its clock in one header chip whose (i) says replay and the fictional
airline; text no model wrote carries only the code mark "{ }", its words in the tooltip and in
screen-reader text. A static check of the page sources, like the inventory tests.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
DESK_FILES = [
    WEB / "desk.html",
    WEB / "desk.js",
    WEB / "doc.html",
    WEB / "doc.js",
    *sorted((WEB / "desk").glob("*.js")),
]
COMMENT = re.compile(r"^\s*(//|/\*|\*|<!--)")
REGEX_LITERAL = re.compile(r"/\^(?:\\.|[^/\n])+/[gimsuy]*")


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    nxt = re.search(r"\n(?:export )?(?:async )?function ", source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def test_no_model_words_are_never_shown_on_the_desk() -> None:
    """The words "NO MODEL" stay only where code reads the server's own text (a pattern, the
    stub's prefix it strips, the label filter); no visible string, chip or suffix says it."""
    allowed = (
        "const STUB_PREFIX = 'NO MODEL: this is the offline stub, "
        "which does not read the question.';",
    )
    for path in DESK_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if COMMENT.match(line) or line.strip() in allowed:
                continue
            rest = REGEX_LITERAL.sub("", line)
            assert "NO MODEL" not in rest, (path.name, line.strip()[:120])
            assert "(NO MODEL)" not in line, (path.name, line.strip()[:120])
            assert "Code only (assistant off)" not in rest, (path.name, line.strip()[:120])


def test_the_header_says_the_assistant_state_once() -> None:
    html = _read("desk.html")
    assert html.count('id="ai-status"') == 1
    assert 'id="budget-chip"' in html
    budget = _read("desk/budget.js")
    # the demo's words, one copy for both pages (wall/x-parts.js stateLine), nothing while on
    line = _function(_read("wall/x-parts.js"), "stateLine")
    assert 'word: "AI off"' in line
    assert 'word: "AI paused"' in line
    assert 'word: "AI unavailable"' in line
    assert "return { word: null," in line
    assert "Offline stub: no model is connected. Code checks still run" in line
    assert "function statusLine(" not in budget
    chip = _function(budget, "drawAiChip")
    assert "const line = stateLine(w, { kind: ai.kind });" in chip
    assert "infoButton({" in chip
    assert "if (line.info)" in chip
    # the label keeps the state for a screen reader in every state, the mark alone while on
    assert "chip.setAttribute('aria-label', w.aria" in chip
    assert "ai.kind === 'on' ? [icon('ta-16')]" in chip
    assert "openBudget" in chip


def test_no_other_desk_view_repeats_the_assistant_state() -> None:
    idle = _read("desk/idle.js")
    assert "aiLead" not in idle
    assert "deskAi" not in idle
    queue = _read("desk/queue.js")
    assert "with TEPHRA Assistant off" not in queue
    review = _read("desk/review.js")
    assert "TEPHRA Assistant off" not in review
    budget = _read("desk/budget.js")
    assert "With no model, no calls are made or counted." not in budget


def test_text_no_model_wrote_carries_the_code_mark_only() -> None:
    ui = _read("desk/ui.js")
    assert "export const CODE_WORDS = 'Written by a code template';" in ui
    mark = _function(ui, "codeMark")
    assert "icon('i-code', 'st')" in mark
    assert "el('span', { class: 'sr-only', text: words })" in mark
    assert "title: words" in mark
    ai = _function(ui, "aiMark")
    assert "if (stub) return codeMark(code);" in ai
    # the AI-written mark is unchanged: the distinction holds when a closed budget leaves some
    # drafts AI-written and some not
    assert "icon('ta-16', 'st')" in ai
    doc = _read("desk/docview.js")
    stub = _function(doc, "modelMark")
    assert "const CODE_WORDS = 'Written by a code template';" in doc
    assert "el('span', { class: 'sr-only', text: CODE_WORDS })" in stub
    assert "'Drafted by TEPHRA Assistant'" in stub


def test_ask_says_the_stub_once_not_on_every_answer() -> None:
    ask = _read("desk/ask.js")
    assert "const STUB_NOTE = 'Answers are code counts: the question is not read.';" in ask
    # defined once, drawn once (above the conversation), never per answer
    assert ask.count("text: STUB_NOTE") == 1
    assert "STUB_NOTE" not in _function(ask, "answerCard")
    words = _function(ask, "stubWords")
    assert "text.replace(STUB_PREFIX, '').trim()" in words
    assert "Code only (assistant off)" not in ask
    # the sub-line and the language line moved into the title's (i)
    assert "infoButton({ topic: 'ask'" in ask
    assert "English, Bahasa Indonesia or Japanese." in ask
    assert "asugg__lang" not in ask


def test_replay_is_one_header_chip_with_the_fictional_airline_behind_its_info() -> None:
    html = _read("desk.html")
    assert 'id="mode-chip"' in html
    chip = _read("desk/modechip.js")
    assert "import { replayWords } from '../wall/x-parts.js';" in chip
    assert "is a fictional airline." in chip
    assert "The clock shows that day, not now." in chip
    assert "el('span', { class: 'dmode__word', text: 'REPLAY' })" in chip
    assert "(replay clock)" in chip
    assert "host.hidden = !replay;" in chip
    # no decision-support chip on the Desk (owner: "don't put this everywhere")
    # (link-preview meta text excepted: it names replay, the fictional airline and decision support)
    for path in DESK_FILES:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "<meta " in line:
                continue
            assert "Decision support only." not in line, (path.name, line.strip()[:120])
    desk = _read("desk.js")
    assert "drawModeChip();" in desk


def test_the_info_button_is_a_real_button_with_its_words_for_screen_readers() -> None:
    """One info component for the demo and the Desk (wall/info.js): the Desk imports it."""
    info = _read("wall/info.js")
    assert '"aria-expanded": "false", "aria-controls": id' in info
    assert '"aria-describedby": sr.id' in info
    assert 'el("span", { id: `${id}-sr`, class: "sr-only", text: said })' in info
    assert 'if (e.key === "Escape" && pops.length) {' in info
    assert "btn?.focus({ preventScroll: true });" in info
    # an (i) inside a label or a row never ticks or opens the thing it sits in
    assert 'btn.addEventListener("click", (e) => e.stopPropagation());' in info
    assert 'if (e.target?.closest?.("a, button")) return;\n    e.preventDefault();' in info
    # the REPLAY chip (face) and the sign-in card's (i) written in the page (wireInfo)
    assert 'btn.classList.add("info__btn--chip");' in info
    assert "export function wireInfo(wrap) {" in info
    assert not (WEB / "desk" / "info.js").exists()
    for name in ("budget.js", "modechip.js", "ask.js", "login.js"):
        assert "from '../wall/info.js';" in _read(f"desk/{name}"), name
    # one look, loaded by both pages
    for page in ("desk.html", "index.html"):
        assert '<link rel="stylesheet" href="/static/info.css">' in _read(page), page
    assert ".info__pop {" not in _read("desk.css")
    assert ".info__pop {" not in _read("wall.css")


def test_sign_in_keeps_every_fact_one_tap_in() -> None:
    html = _read("desk.html")
    assert "Your decisions are public." in html
    sr = html.split('id="visitor-facts-sr" class="sr-only">')[1].split("</span>")[0]
    assert "public record as visitor:&lt;your name&gt;" in sr
    assert "Visitors cannot change the display or the feeds." in sr
    assert '<span id="login-pin-sr" class="sr-only">The PIN is never stored.</span>' in html
    assert "login__steps" not in html
    assert "wireInfo(wrap)" in _read("desk/login.js")


def test_the_ai_words_are_the_last_thing_the_header_drops() -> None:
    """Honesty verify, 17 Oct: at 390 px the header hid "AI off" first and showed only a dot. The
    words go last now, after the connection words, the compact wordmark and REPLAY chip, the (i),
    the dot, the REPLAY glyph and the REPLAY clock."""
    fit = _function(_read("desk/budget.js"), "fitHead")
    order = [
        "'is-tight'",
        "'is-tighter'",
        "'is-tightest'",
        "'is-tiniest'",
        "chip.classList.add('is-tight')",
    ]
    at = [fit.index(x) for x in order]
    assert at == sorted(at)
    css = _read("desk.css")
    assert ".dhead__row.is-tightest #ai-status .info {" in css
    assert ".dhead__row.is-tiniest .dmode__clock {" in css


def test_an_ask_answer_leads_with_its_code_mark() -> None:
    """UX verify, 17 Oct: the "{ }" beside the language chip read as if the language were
    code-made; a code answer's mark leads its words, a model's mark stays in the foot."""
    ask = _read("desk/ask.js")
    assert "lead.prepend(mark, ' ');" in ask
    # the Desk's code mark is `ai-mark--none` (desk/ui.js codeMark)
    assert "mark.classList.contains('ai-mark--none')" in ask
    assert "class: 'ai-mark ai-mark--none'" in _read("desk/ui.js")
    assert "byCode && lead ? null : mark," in ask
