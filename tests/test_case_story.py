"""The case strip's words (tephra/web/data/cases.json, wall/case.js): every number a claims-register
row in research/README.md, every cited row real, and no phrase from the never-say list in
docs/PITCH.md. Entries whose replay case folder is absent (the public export drops one) are skipped.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tephra" / "web" / "data" / "cases.json"
REGISTER = ROOT / "research" / "README.md"
PITCH = ROOT / "docs" / "PITCH.md"
REPLAY = ROOT / "data" / "replay"
TEXT_FIELDS = ("eyebrow", "happened", "disagreed", "sources")
ROW_FIELDS = ("happened_rows", "disagreed_rows")


def _entries() -> dict[str, dict]:
    return json.loads(CASES.read_text(encoding="utf-8"))


def _kept() -> list[tuple[str, dict]]:
    return [(cid, e) for cid, e in _entries().items() if (REPLAY / cid).is_dir()]


def _digit_tokens(text: str) -> set[str]:
    """Every `\\d[\\d,.]*` token, without a trailing full stop or comma from the sentence."""
    return {tok.rstrip(".,") for tok in re.findall(r"\d[\d,.]*", text)}


def _register_rows() -> set[int]:
    rows = set()
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|", line)
        if m:
            rows.add(int(m.group(1)))
    return rows


def _never_say() -> list[str]:
    text = PITCH.read_text(encoding="utf-8")
    start = text.index("## Never say")
    rest = text[start:].split("\n## ", 1)[0]
    phrases: list[str] = []
    for line in rest.splitlines():
        if not line.startswith("- "):
            continue
        # the permitted wording that follows "Say" or "Prefer" on the same line is not forbidden
        cut = re.split(r' Say "| Prefer ', line, maxsplit=1)[0]
        phrases.extend(p.strip().lower() for p in re.findall(r'"([^"]+)"', cut) if p.strip())
    return phrases


def test_the_cases_file_has_the_shape_the_strip_reads() -> None:
    entries = _entries()
    assert entries, "no entries"
    for cid, e in entries.items():
        assert set(e) == {*TEXT_FIELDS, *ROW_FIELDS}, cid
        assert isinstance(e["happened"], str), cid
        assert e["happened"], cid
        for key in ROW_FIELDS:
            assert all(isinstance(r, int) for r in e[key]), (cid, key)


def test_every_shipped_replay_case_has_an_entry() -> None:
    cases = {p.name for p in REPLAY.iterdir() if p.is_dir() and (p / "manifest.json").exists()}
    assert cases <= set(_entries()), cases - set(_entries())


@pytest.mark.parametrize("cid", [cid for cid, _ in _kept()])
def test_every_number_in_a_kept_entry_is_in_the_claims_register(cid: str) -> None:
    """Each of "23", "27", "6" and "2026" counts; one the register does not hold is invented."""
    register = _digit_tokens(REGISTER.read_text(encoding="utf-8"))
    entry = _entries()[cid]
    for field in TEXT_FIELDS:
        for tok in _digit_tokens(entry[field] or ""):
            assert tok in register, (cid, field, tok)


@pytest.mark.parametrize("cid", [cid for cid, _ in _kept()])
def test_every_cited_row_exists(cid: str) -> None:
    rows = _register_rows()
    entry = _entries()[cid]
    for key in ROW_FIELDS:
        for r in entry[key]:
            assert r in rows, (cid, key, r)


def test_no_never_say_phrase_reaches_the_strip() -> None:
    phrases = _never_say()
    assert phrases, "the never-say list was not found"
    for cid, e in _entries().items():
        text = " ".join(e[f] or "" for f in TEXT_FIELDS).lower()
        for phrase in phrases:
            assert phrase not in text, (cid, phrase)


def test_the_semeru_dates_keep_the_register_en_dash() -> None:
    dates = "23–27 Sep"  # noqa: RUF001  the register's en dash, kept as written
    assert dates in _entries()["semeru-20260923"]["disagreed"]
    assert dates in REGISTER.read_text(encoding="utf-8")


def test_the_eyebrow_never_states_an_alert_level() -> None:
    """Never-say row 38: two official sources disagree on Anak Krakatau's level."""
    for cid, e in _entries().items():
        assert not re.search(r"\blevel\b", (e["eyebrow"] or "").lower()), cid
    assert _entries()["anak-krakatau-20260905"]["eyebrow"] == "Colour code red"


def test_the_strip_says_the_ash_area_and_who_decides() -> None:
    case_js = (ROOT / "tephra" / "web" / "wall" / "case.js").read_text(encoding="utf-8")
    assert "export function caseStrip(" in case_js
    assert "heading into the ash area" in case_js
    assert "drafts an advisory a dispatcher decides" in case_js
    assert 'mode !== "REPLAY"' in case_js
    # one read of the file, here; the story draws the strip as soon as the words are in
    assert case_js.count("fetch(") == 1
    assert 'fetch("/static/data/cases.json"' in case_js
    story = (ROOT / "tephra" / "web" / "wall" / "story.js").read_text(encoding="utf-8")
    assert "loadCases(() => { if (lastStory) renderStory(...lastStory); });" in story
    index = (ROOT / "tephra" / "web" / "index.html").read_text(encoding="utf-8")
    assert 'id="case-strip"' in index
    assert index.index('id="case-strip"') < index.index('id="headline"')
