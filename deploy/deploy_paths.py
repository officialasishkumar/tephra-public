"""Which changed files make a push deploy: the `paths:` filter of .github/workflows/deploy.yml.

    git diff --no-renames --name-only A B | python3 -I deploy/deploy_paths.py WORKFLOW_FILE

prints the paths read on stdin that the workflow's push filter matches (the ones that would
start a deploy run), one per line. deploy/cloudrun.sh uses it in CI mode to decide whether a
newer commit on main will deploy by itself. The patterns are read from the workflow file, so
there is one list. Exit status 2 when the filter cannot be read or uses a pattern this file
does not understand; the caller must then not assume anything.

Pattern rules are GitHub's (docs: "Filter pattern cheat sheet"): `*` is any run of characters
except `/`, `**` any run of characters, a leading `!` excludes, and the last pattern that
matches a path decides. Only `*`, `**` and `!` are supported here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_UNSUPPORTED = set("?+[]{}\\")


def read_patterns(workflow_text: str) -> list[str]:
    """The `paths:` list under `on: push:` (block style, as deploy.yml writes it)."""
    lines = workflow_text.splitlines()
    patterns: list[str] = []
    in_on = in_push = in_paths = False
    on_indent = push_indent = paths_indent = -1
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if in_paths:
            if indent > paths_indent and stripped.startswith("- "):
                item = stripped[2:].split(" #", 1)[0].strip()
                if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
                    item = item[1:-1]
                patterns.append(item)
                continue
            break
        if in_push and indent <= push_indent:
            in_push = False
        if in_on and indent <= on_indent:
            in_on = False
        if not in_on and stripped in ("on:", '"on":', "'on':"):
            in_on, on_indent = True, indent
        elif in_on and not in_push and stripped == "push:":
            in_push, push_indent = True, indent
        elif in_push and stripped == "paths:":
            in_paths, paths_indent = True, indent
    if not patterns:
        raise ValueError("no on.push.paths list in the workflow")
    return patterns


def _regex(pattern: str) -> re.Pattern[str]:
    if _UNSUPPORTED & set(pattern) or not pattern:
        raise ValueError(f"unsupported path pattern {pattern!r}")
    out = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def compile_filter(patterns: list[str]) -> list[tuple[bool, re.Pattern[str]]]:
    rules = []
    for pattern in patterns:
        include = not pattern.startswith("!")
        rules.append((include, _regex(pattern if include else pattern[1:])))
    return rules


def triggers(path: str, rules: list[tuple[bool, re.Pattern[str]]]) -> bool:
    decision = False
    for include, regex in rules:
        if regex.match(path):
            decision = include
    return decision


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"usage: {argv[0]} WORKFLOW_FILE < changed-paths", file=sys.stderr)
        return 2
    try:
        rules = compile_filter(read_patterns(Path(argv[1]).read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        print(f"deploy_paths: {exc}", file=sys.stderr)
        return 2
    for line in sys.stdin:
        path = line.rstrip("\n")
        if path and triggers(path, rules):
            print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
