"""AI, quietly (docs/UI-AI-QUIET.md section 6): a static check of the page sources, like the
inventory test. AI health has one home, AI failures never use the picture's red or role=alert,
model ids stay out of visible chip text, and the honesty fixes (section 4) stay in place.
"""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    pattern = r"\n(?:export )?(?:async )?function |\nconst [A-Za-z_]+ = \("
    nxt = re.search(pattern, source[start + 1 :])
    return source[start : start + 1 + nxt.start()] if nxt else source[start:]


def test_story_failures_hold_only_the_picture() -> None:
    """Q4: the red banner is for feeds, the database, the connection, the map and the page."""
    body = _function(_read("wall/story.js"), "storyFailures")
    for key in ("plan-", "sat-", "duty-", "trace-fails"):
        assert f"key: `{key}" not in body, key
    assert "aiStopClause" not in body


def test_ai_builders_use_no_red_and_no_alert() -> None:
    ui = _read("desk/ui.js")
    card = _function(ui, "unavailableCard")
    # the AI branch is caution and role=status; only a connection or session failure is serious
    assert "panel--caution unavail', role: 'status'" in card
    mark = _function(ui, "aiMark")
    assert "serious" not in mark
    assert "alert" not in mark
    failures = _read("desk/failures.js")
    # the hand-plan group; a failed save ("Not saved") is not an AI failure and stays red
    for name in ("row", "group", "renderFailures"):
        body = _function(failures, name)
        assert "serious" not in body, name
        assert "alert" not in body, name
    xparts = _read("wall/x-parts.js")
    for name in ("aiMark", "aiWords", "aiLead"):
        assert "serious" not in _function(xparts, name), name


def test_ai_chip_text_carries_no_model_id() -> None:
    panels = _read("wall/panels.js")
    chip = panels[panels.index("// The AI chip (R3.1") : panels.index("// Data chip:")]
    assert "llm?.label" not in chip
    assert "model_id" not in chip
    budget = _function(_read("desk/budget.js"), "drawAiChip")
    assert "model_id" not in budget
    assert "label" in budget
    story = _read("wall/story.js")
    trust = story[story.index("const TRUST = ") : story.index("// The hero:")]
    assert "model" not in trust.lower()


def test_writer_lines_name_no_model() -> None:
    queue = _read("desk/queue.js")
    assert "Drafted by AI (" not in queue
    review = _read("desk/review.js")
    assert "Drafted by AI (" not in review


def test_estimate_outcome_has_explicit_pending_and_official_only() -> None:
    body = _function(_read("wall/panels.js"), "estimateOutcome")
    assert 'outcome === "PENDING"' in body
    assert 'outcome === "OFFICIAL_ONLY"' in body
    assert "MODEL_READ.has(outcome)" in body


def test_how_the_model_read_it_is_gated_on_the_outcome() -> None:
    body = _function(_read("wall/panels.js"), "areaSection")
    assert "MODEL_READ.has(outcome)" in body
    assert '"How the Plume reader read it"' in body
    assert '"How TEPHRA built it"' in body


def test_duty_officer_budget_outcome_exists() -> None:
    duty = _read("wall/duty.js")
    assert re.search(r"\bBUDGET: \[", duty)
    assert "outcomeOf" in duty


def test_dead_model_chip_is_gone() -> None:
    assert "export function modelChip" not in _read("desk/queue.js")
    desk = "".join(p.read_text(encoding="utf-8") for p in (WEB / "desk").glob("*.js"))
    assert "aiChip" not in desk


def test_one_ai_state_on_both_pages() -> None:
    xparts = _read("wall/x-parts.js")
    assert "export function aiStateOf(" in xparts
    assert "export function aiState(" in _read("wall/ext.js")
    assert "export function aiState(" in _read("desk/ui.js")
    # causes are keyed by helper and reason class, never by the rendered sentence
    assert "const key = `${helperKey}|${cls}`;" in xparts


def test_budget_refusals_outside_the_pause_stay_a_problem() -> None:
    """Review H1: only a lite-model budget refusal during the pause is part of the pause; a
    lane's share or the Plume Reader's own model running out is a problem in every state."""
    body = _function(_read("wall/x-parts.js"), "aiStateOf")
    assert 'absorbed: paused && g.reasonClass === "budget" && !g.main' in body
    assert "const trouble = causes.filter((c) => !c.absorbed);" in body
    assert "mainModel(budget)" in body


def test_duty_officer_that_ran_is_never_called_unavailable() -> None:
    """Review H2: a run that answered and left must-do work is "undone", on both pages."""
    xparts = _read("wall/x-parts.js")
    assert "DUTY OFFICER DID NOT DISPATCH" in _function(xparts, "reasonClass")
    assert "block.undone" in _function(xparts, "handPlanOf")
    assert "cls === 'undone'" in _function(_read("desk/failures.js"), "causeWords")


def test_reset_time_never_reads_as_replay_clock_time() -> None:
    """Review H4: the reset is on the real clock. In REPLAY it is said as the time left
    ("for another 2 h 45 min"), which reads the same on either clock."""
    xparts = _read("wall/x-parts.js")
    assert "realWhen(Date.parse(budget?.resets_at" in _function(xparts, "aiStateOf")
    assert "for another ${left}" in _function(xparts, "realWhen")
    assert 'replay: D?.mode === "REPLAY"' in _read("wall/ext.js")
    assert "app.state.mode === 'REPLAY'" in _read("desk/budget.js")


def test_failed_checks_run_is_not_not_run_and_has_no_ai_mark() -> None:
    """Review H5: a Duty Officer run that called the model is "No brief", never "Not run", and
    its failed brief carries no AI-written mark."""
    duty = _read("wall/duty.js")
    assert 'MODEL_FAILED: ["caution", "No brief"' in duty
    assert 'run.outcome === "MODEL_FAILED" ? null : run.model_id' in duty


def test_recovery_data_failures_stay_red() -> None:
    """Review H7: a recovery step code could not run (no schedule) is a data failure. The Wall's
    chip (ext.js aiState) and AI at work (board.js) both read the trace through aiErrorsOf."""
    errors = _function(_read("wall/x-parts.js"), "aiErrorsOf")
    assert '!(t.stage === "RECOVERY" && t.actor === "system")' in errors
    assert "aiErrorsOf(store?.trace)" in _function(_read("wall/ext.js"), "aiState")
    assert "aiErrorsOf(input.trace)" in _read("wall/board.js")
    assert 'key: "recovery-data"' in _function(_read("wall/story.js"), "storyFailures")


# The retired words of the first build (docs/UI-AI-QUIET.md, Naming): the AI is shown as one
# assistant, "TEPHRA Assistant", whose skills are named by job.
OLD_WORDS = (
    "AI-written",
    "AI-read",
    "AI-chosen",
    "Code (AI off)",
    "AI helpers",
    "AI at work",
    "AI paused",
    "AI waiting",
    "AI unavailable",
    "AI today",
    "AI off",
    "AI on",
)
COMMENT = re.compile(r"^\s*(//|/\*|\*|<!--)")
REGEX_LITERAL = re.compile(r"/(?:\\.|[^/\n])+/[gimsuy]*")
# the reason code writes for a run that left must-do work, as the server words it (raw)
RAW_REASON = "`Duty Officer left ${left} mandatory item(s) undone: to the Desk`"


def _page_sources() -> dict[str, str]:
    files = [*WEB.glob("*.html"), *WEB.glob("*.js"), *(WEB / "wall").glob("*.js")]
    files += list((WEB / "desk").glob("*.js"))
    return {p.name: p.read_text(encoding="utf-8") for p in files}


def test_one_assistant_name_and_no_old_ai_words() -> None:
    """Naming: the old "AI …" words are gone from every page string (comments may cite them),
    and "Duty Officer" is left only in the patterns that read the code's raw lines."""
    xparts = _read("wall/x-parts.js")
    assert 'export const ASSISTANT = "TEPHRA Assistant";' in xparts
    assert 'duty: "Coordinator"' in xparts
    for name, source in _page_sources().items():
        code = [line for line in source.splitlines() if not COMMENT.match(line)]
        for word in OLD_WORDS:
            assert not any(word in line for line in code), (name, word)
        for line in code:
            rest = REGEX_LITERAL.sub("", line.replace(RAW_REASON, "")).split("//")[0]
            assert "Duty Officer" not in rest, (name, line)


def test_the_disclosure_still_says_ai() -> None:
    """Naming: "AI" stays where disclosure needs it: the chip tooltip, the About lines and the
    free AI quota at the assistant's home; and the chip still says it never shrinks the official
    area. The quota is said in the home's lead only, never in the chip (8.6)."""
    xparts = _read("wall/x-parts.js")
    words = _function(xparts, "aiWords")
    assert "assistantIs()" in words
    assert "TEPHRA Assistant is TEPHRA's AI assistant (${modelFamily})." in xparts
    assert "never shrink the official area" in words
    assert "quota" not in words
    assert "Google's free daily AI quota" in _function(xparts, "aiLead")
    about = "TEPHRA Assistant is an AI assistant. It reads feeds and drafts text."
    assert about in _function(_read("wall/controls.js"), "aboutContent")
    assert about in _read("wall/controls.js")
    assert about in _read("desk/budget.js")
    # no first-use card on either page (13 Oct 2026): the line is one click away, in About and the
    # assistant sheet, and in the chip's tooltip
    for page in ("index.html", "desk.html"):
        assert 'id="firstuse"' not in _read(page), page


def test_a_run_no_model_called_is_not_credited_to_the_assistant() -> None:
    """Naming review: code starts every Coordinator run; the run's facts never say the assistant
    ran it when the quota refused the call or no model is connected."""
    assert '["Started", run.trigger === "adsb" ? "by code' in _read("wall/duty.js")
    assert "TEPHRA Assistant after" not in _read("desk/duty.js")
    assert "Run by" not in _read("wall/duty.js")


def test_the_strata_mark_is_in_the_sprite() -> None:
    icons = _read("icons.svg")
    for symbol in ("ta-64", "ta-16", "ta-working", "ta-waiting", "ta-unavailable"):
        assert f'<symbol id="{symbol}"' in icons, symbol
    marks = icons[icons.index('<symbol id="ta-64"') :]
    assert "style=" not in marks
    assert "#" not in marks.replace("</svg>", "")


# Say the cause once (docs/UI-AI-QUIET.md 8.6): the free quota, budgets, per-model counts, lanes,
# pacing and reset or slot times are said at the assistant's home only (Details, TEPHRA Assistant;
# the Desk's assistant sheet: desk/budget.js, wall/duty.js). Every other page source says
# "paused" and what to do; the raw reasons are matched by regex literals and comments only.
# wall/ext.js and wall/x-parts.js hold main-view places too (Satellite picture, Airport closures,
# the plain words, the story's and board's words), so they are scanned with the home's own
# builders left out (HOME_ONLY); tests/test_wall_board.py runs the shared words on a quota refusal.
MAIN_VIEW_SOURCES = (
    "wall/ext.js",
    "wall/x-parts.js",
    "wall/story.js",
    "wall/panels.js",
    "wall/details.js",
    "wall/board.js",
    "wall/board-view.js",
    "wall/derive.js",
    "wall/map.js",
    "wall/ext-map.js",
    "wall/controls.js",
    "desk/failures.js",
    "desk/ask.js",
    "desk/network.js",
    "desk/docs.js",
    "desk/idle.js",
    "desk/review.js",
    "desk/queue.js",
    "desk/duty.js",
    "desk/ui.js",
    "index.html",
    "desk.html",
)
QUOTA_TEXT = re.compile(
    r"quota|used up|closed by google|free ai|next slot|\bspent\b|calls today|calls left"
    r"|share of calls|\bpacing\b|resets? (?:at|once)|reset was due|AI budget",
    re.I,
)
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
# The builders that draw the assistant's home (Details, TEPHRA Assistant), where the cause is said.
HOME_ONLY = {
    "wall/x-parts.js": ("aiLead",),
    "wall/ext.js": ("agentStatus", "workWords", "budgetBlock", "waitingTail", "budgetTile"),
}
# One-line constants of the home's words: the cause in full (WHY.budget) and the queue's pacing.
HOME_CONSTS = ("export const pacingWords = ", '  budget: "today\'s free AI quota is used up"')


def _main_view(rel: str) -> str:
    source = _read(rel)
    for name in HOME_ONLY.get(rel, ()):
        source = source.replace(_function(source, name), "")
    return "\n".join(line for line in source.splitlines() if not line.startswith(HOME_CONSTS))


def test_main_views_never_say_why_the_assistant_is_paused() -> None:
    for rel in MAIN_VIEW_SOURCES:
        source = _main_view(rel)
        for line in source.splitlines():
            if COMMENT.match(line):
                continue
            code = REGEX_LITERAL.sub("", line) if rel.endswith(".js") else line
            html = [re.sub(r"<!--.*?-->", "", code)]
            texts = STRING.findall(code) if rel.endswith(".js") else html
            for text in texts:
                assert not QUOTA_TEXT.search(text), (rel, line.strip()[:140])


def test_the_cause_of_a_pause_is_one_tap_from_every_place_that_lacks_an_output() -> None:
    """Rule 9 at the place, with the cause one tap away (8.6): each place that has no assistant
    output while it is paused still says so and what to do, and links to the assistant's home."""
    panels = _read("wall/panels.js")
    assert "No advisory drafts for ${whose}. " in panels
    # paused, or a skill that did not run or gave no result: "Why" either way
    assert 'hand.block.paused || hand.block.unavailable ? [" ", whyLink("flights-why")]' in panels
    assert 'hand.block.paused || hand.block.unavailable ? [" ", whyLink("dec-why")]' in panels
    details = _read("wall/details.js")
    assert '"No advisory draft for this flight. "' in details
    assert 'b.paused || b.unavailable ? [" ", whyLink("fdetail-why")]' in details
    ext = _read("wall/ext.js")
    assert 'A new plan waits in line for ${ASSISTANT}. `, whyLink("rec-why")' in ext
    # the Satellite picture: "paused" only while the assistant is, and the cause one tap away
    sat = _function(ext, "satRow")
    assert 'kind === "paused" ? `${ASSISTANT} is paused` : "Satellite reader did not run"' in sat
    assert "Nothing was put in its place." in sat
    assert 'not read. Nothing was put in ${bad === 1 ? "its" : "their"} place' in ext
    assert 'whyLink("sat-why")' in ext
    xparts = _read("wall/x-parts.js")
    why = xparts[xparts.index("export const whyLink = ") :]
    assert 'dataset: { act: "details-sec", sec: "ai", focus }' in why[: why.index("\n")]
    story = _read("wall/story.js")
    assert "`${ASSISTANT} · paused`" in story
    assert 'why: aiCause ? { act: "ai", text: "Why \u203a"' in story
    failures = _read("desk/failures.js")
    hand = "No advisory drafts for ${n === 1 ? 'this flight' : `these ${n} flights`}. Plan"
    assert hand in failures
    assert "'data-why': '1'" in failures
    # the list replaces Decide on a phone: it has its own "Why" link (review clutter 1)
    pane = _function(failures, "paneBody")
    assert "'Decide each flight by hand, then mark it handled.'" in pane
    assert "onclick: openBudget" in pane
    ask = _read("desk/ask.js")
    assert "title: 'TEPHRA Assistant is paused.'" in ask
    assert "onWhy: openBudget" in ask
    assert "TEPHRA Assistant is paused, so Ask cannot answer yet." in ask
    # "paused" only while the assistant is; the question goes back into the box
    assert "paused = quota && deskAi().kind === 'paused';" in ask
    assert "composer.input.value = question;" in _function(ask, "finish")
    for rel in ("desk/network.js", "desk/docs.js"):
        assert "'Why: open the TEPHRA Assistant sheet', onclick: openBudget" in _read(rel), rel
    # the homes keep the reason, the models' calls and the queue's slots
    assert "Closed for today by Google" in _read("desk/budget.js")
    assert "Google closed the free quota after" in ext
    assert "Today's free AI quota is used up: no model was called." in _read("wall/duty.js")
