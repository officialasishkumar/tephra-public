"""README.md is written for a reader of the public repository: no text addressed to the people
who score it, every real-world number a row of the claims register, every link a path the export
keeps, and mermaid labels quoted (an unquoted label with a dot, a colon or parentheses breaks the
GitHub renderer)."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
REGISTER = ROOT / "research" / "README.md"
DROP_LIST = ROOT / "deploy" / "public" / "drop.txt"

ADDRESSED = re.compile(r"\bjudges?\b|\bjudging\b|\bjudged\b|submission|rubric|evaluat", re.I)
ROW = re.compile(r"<!-- row (\d+) -->")
LINK = re.compile(r"\]\(([^)\s]+)\)")
REGISTER_ROW = re.compile(r"^\| (\d+) \|")
# A mermaid node or edge label that is not quoted: ID[text], ID([text]), ID{text}, |text|.
NODE_OPENER = re.compile(r"^\s*\w+([\[({]+)")
UNQUOTED_EDGE = re.compile(r"\|(?!\")[^|\n]*\|")


def _readme() -> str:
    return README.read_text(encoding="utf-8")


def _register_rows() -> set[int]:
    rows: set[int] = set()
    inside = False
    for line in REGISTER.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.startswith("## Claims register")
            continue
        match = REGISTER_ROW.match(line)
        if inside and match:
            rows.add(int(match.group(1)))
    return rows


def _dropped_patterns() -> list[str]:
    patterns = []
    for raw in DROP_LIST.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            patterns.append(line)
    return patterns


def _is_dropped(relpath: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith("/") and relpath.startswith(pattern):
            return True
        if any(ch in pattern for ch in "*?[") and Path(relpath).match(pattern):
            return True
        if relpath == pattern:
            return True
    return False


def _unquoted_node(part: str) -> bool:
    match = NODE_OPENER.match(part)
    return bool(match) and not part[match.end() :].startswith('"')


def test_readme_has_no_judge_or_rubric_words() -> None:
    hits = [line for line in _readme().splitlines() if ADDRESSED.search(line)]
    assert not hits, hits


def test_every_readme_number_cites_a_register_row() -> None:
    cited = [int(n) for n in ROW.findall(_readme())]
    assert len(cited) >= 20, len(cited)
    rows = _register_rows()
    assert len(rows) >= 45, len(rows)
    unknown = sorted({n for n in cited if n not in rows})
    assert not unknown, unknown


def test_readme_links_resolve_inside_the_export() -> None:
    if not DROP_LIST.exists():
        pytest.skip("no export drop list in this tree")
    patterns = _dropped_patterns()
    problems = []
    for target in LINK.findall(_readme()):
        if "://" in target or target.startswith(("#", "mailto:")):
            continue
        relpath = target.split("#", 1)[0]
        if not (ROOT / relpath).exists():
            problems.append(f"missing: {target}")
        elif _is_dropped(relpath, patterns):
            problems.append(f"dropped by the export: {target}")
    assert not problems, problems


def test_readme_mermaid_labels_are_quoted() -> None:
    text = _readme()
    blocks = re.findall(r"```mermaid\n(.*?)```", text, re.S)
    assert len(blocks) == 2, len(blocks)
    problems = []
    for block in blocks:
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("flowchart", "subgraph", "end", "%%")):
                continue
            for part in re.split(r"-->|-\.->|---", stripped):
                if _unquoted_node(part.strip()) or UNQUOTED_EDGE.search(part):
                    problems.append(stripped)
                    break
    assert not problems, problems


def test_the_onboarding_limits_are_said_where_onboarding_is() -> None:
    """The account comes first, a dispatcher verifies each airline, and running a verified airline
    on this site is not switched on: the README says so beside the offer. The setup kit and the
    self-hosting offer went (owner, 17 Oct 2026: "drop it"); the README no longer says the airline's
    TEPHRA drafts under Ring of Fire Air numbers (batch 2 honesty finding 3)."""
    section = _readme().split("### Onboard your airline", 1)[1].split("**How to onboard", 1)[0]
    flat = " ".join(section.split())
    assert "an account first, then nine short pages" in flat
    assert "A TEPHRA dispatcher verifies each airline." in flat
    assert "Running a verified airline on this site is not switched on yet." in flat
    assert "Ring of Fire Air number" not in flat
    readme = _readme()
    for gone in ("setup kit", "run its own TEPHRA", "Run your own TEPHRA", "file by file"):
        assert gone not in readme, gone
