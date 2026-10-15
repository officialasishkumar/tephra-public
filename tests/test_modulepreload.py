"""Each page lists every module its entry script imports as a modulepreload, so the browser fetches
the whole module graph at once instead of one import level per round trip (about 160 ms a level on
the live service). A module added to the graph without its link fails here, with the line to add.
"""

import re
from pathlib import Path

import pytest

WEB = Path(__file__).resolve().parents[1] / "tephra" / "web"
PAGES = {
    "index.html": "wall.js",
    "desk.html": "desk.js",
    "connect.html": "connect.js",
    "guide.html": "guide.js",
    "doc.html": "doc.js",
}
IMPORT = re.compile(
    r"""^\s*(?:import|export)\s[^;]*?from\s+["'](\.{1,2}/[^"']+)["']"""
    r"""|^\s*import\s+["'](\.{1,2}/[^"']+)["']""",
    re.M,
)
PRELOAD = re.compile(r'<link rel="modulepreload" href="([^"]+)">')


def _closure(entry: str) -> set[str]:
    """Every module the entry reaches through static imports (a dynamic import() stays lazy)."""
    root = WEB.resolve()
    seen: set[Path] = set()
    todo = [root / entry]
    while todo:
        current = todo.pop()
        for m in IMPORT.finditer(current.read_text(encoding="utf-8")):
            target = (current.parent / (m.group(1) or m.group(2))).resolve()
            if target not in seen:
                seen.add(target)
                todo.append(target)
    return {f"/static/{p.relative_to(root).as_posix()}" for p in seen}


@pytest.mark.parametrize(("page", "entry"), PAGES.items())
def test_every_imported_module_is_preloaded(page: str, entry: str) -> None:
    html = (WEB / page).read_text(encoding="utf-8")
    listed = set(PRELOAD.findall(html))
    needed = _closure(entry)
    missing = sorted(needed - listed)
    extra = sorted(listed - needed)
    assert not missing, (
        "add to "
        + page
        + ": "
        + " ".join(f'<link rel="modulepreload" href="{m}">' for m in missing)
    )
    assert not extra, f"{page} preloads modules {entry} no longer imports: {extra}"
