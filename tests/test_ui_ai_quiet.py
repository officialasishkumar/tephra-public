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
    trust = _function(_read("wall/story.js"), "renderTrust")
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
    assert '"How the model read it"' in body
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
