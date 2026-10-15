"""docs/GLOSSARY.md is the one vocabulary: retired words stay out of the documents a reader
meets first and out of every page string. Code identifiers, raw trace patterns and backticked
spans are exempt (the raw trace lines keep the code's own names)."""

import re
from pathlib import Path

from tests.test_ui_ai_quiet import COMMENT, RAW_REASON, REGEX_LITERAL

ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    "README.md",
    "docs/ARCHITECTURE.md",
    "docs/GLOSSARY.md",
    "docs/PITCH.md",
    "docs/EVALS.md",
    "tephra/web/THIRD_PARTY.md",
]
RETIRED = [
    "Duty Officer",
    "Exposure Planner",
    "Dispatch Drafter",
    "AI helper",
    "hazard cone",
    "cautious hazard area",
    "SRA drafter",
    "Satellite Reader",
    "Plume Reader",
    "Notice Reader",
]
BACKTICK = re.compile(r"`[^`]*`")
# board.js and x-parts.js patterns that read the code's raw trace lines ("Duty Officer: ...")
RAW_LINE = re.compile(r"/\^?Duty Officer[^/]*/")


def _prose(text: str) -> str:
    return BACKTICK.sub("", text)


def _page_files() -> list[Path]:
    web = ROOT / "tephra" / "web"
    return [
        *web.glob("*.html"),
        *web.glob("*.js"),
        *(web / "wall").glob("*.js"),
        *(web / "desk").glob("*.js"),
    ]


def test_documents_use_the_glossary_words() -> None:
    for rel in DOCS:
        prose = _prose((ROOT / rel).read_text(encoding="utf-8"))
        hits = [w for w in RETIRED if w in prose]
        assert not hits, (rel, hits)


def test_page_strings_use_the_glossary_words() -> None:
    for path in _page_files():
        for line in path.read_text(encoding="utf-8").splitlines():
            if COMMENT.match(line):
                continue
            rest = RAW_LINE.sub("", line.replace(RAW_REASON, ""))
            rest = REGEX_LITERAL.sub("", rest).split("//")[0]
            hits = [w for w in RETIRED if w in rest]
            assert not hits, (path.name, hits, line.strip()[:120])


def test_glossary_names_every_board_skill() -> None:
    board = (ROOT / "tephra/web/wall/board.js").read_text(encoding="utf-8")
    # The roster rows only ({ id, role, name, ... }); the gate labels below them are not skills.
    names = re.findall(r'\{ id: "\w+", role: "\w+", name: "([^"]+)"', board)
    assert len(names) >= 9, names
    glossary = (ROOT / "docs/GLOSSARY.md").read_text(encoding="utf-8")
    missing = [n for n in names if f"| {n} |" not in glossary]
    assert not missing, missing
