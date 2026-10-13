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
    free AI quota; and the chip still says it never shrinks the official area."""
    words = _function(_read("wall/x-parts.js"), "aiWords")
    assert "TEPHRA Assistant is TEPHRA's AI assistant (Gemini)." in words
    assert "never shrink the official area" in words
    assert "today's free AI quota is used up" in words
    about = "TEPHRA Assistant is an AI assistant. It reads feeds and drafts text."
    assert about in _read("wall/controls.js")
    assert about in _read("desk/budget.js")


def test_the_strata_mark_is_in_the_sprite() -> None:
    icons = _read("icons.svg")
    for symbol in ("ta-64", "ta-16", "ta-working", "ta-waiting", "ta-unavailable"):
        assert f'<symbol id="{symbol}"' in icons, symbol
    marks = icons[icons.index('<symbol id="ta-64"') :]
    assert "style=" not in marks
    assert "#" not in marks.replace("</svg>", "")
