"""Details > Runs on (SPEC T09 B07): one section, drawn from ``SystemState.cloud`` with no model id,
and the audit chain said "intact" only when this instance walked it (``state.audit.intact``), else
"checking"."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
MODEL_ID = re.compile(r"gemini-\d|gemini-[a-z]+-|flash\b|models/", re.I)


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    match = re.search(rf"^(?:export )?(?:function|const) {name}\b", source, re.M)
    assert match, name
    end = re.search(r"^(?:export )?(?:function|const) |^// -{10,}", source[match.end() :], re.M)
    return source[match.start() : match.end() + (end.start() if end else len(source))]


def test_runs_on_is_listed_once_behind_the_scenes() -> None:
    details = _read("wall/details.js")
    rows = [line for line in details.splitlines() if 'title: "Runs on"' in line]
    assert len(rows) == 1
    row = 'key: "runs", group: "Behind the scenes", title: "Runs on", host: "xpanel", xtab: "runs"'
    assert row in rows[0]
    assert 'case "runs":' in details
    assert "runs: runsPanel" in _read("wall/ext.js")


def test_the_runs_section_names_no_model() -> None:
    ext = _read("wall/ext.js")
    for name in ("runsRows", "auditLine", "runsStatus", "runsPanel"):
        body = _function(ext, name)
        assert not MODEL_ID.search(body), name
        assert "model_id" not in body, name
    rows = _function(ext, "runsRows")
    texts = (
        "Cloud Run · ",
        '"Revision"',
        "Firestore",
        "Cloud Scheduler · every minute",
        "Secret Manager",
        "Gemini API",
        "One instance, one writer",
        "This computer · ",
    )
    for text in texts:
        assert text in rows, text


def test_intact_is_said_only_when_this_instance_walked_the_chain() -> None:
    body = _function(_read("wall/ext.js"), "auditLine")
    intact = [line for line in body.splitlines() if "Audit chain intact" in line]
    assert len(intact) == 1
    assert intact[0].strip().startswith("if (audit.intact) return")
    assert 'if (!audit) return { text: "Audit chain: checking"' in body
    assert "not yet walked" in body, "a restored head that was not walked here still says checking"
    assert 'Audit chain: ${plural(problems.length, "problem")}' in body
