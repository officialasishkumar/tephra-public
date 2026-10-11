"""Remove registrations and non-airline aircraft from a recorded ADS-B replay leg.

adsb.lol answers carry each aircraft's registration (``r``) and database flags
(``dbFlags``, bit 0 = military). Registrations of business jets and light aircraft can
identify private people (research/06), and the app itself never keeps ``r``. This script
rewrites the ``raw/adsb/`` answers of one replay case so that:

- a target is dropped when its callsign is not an airline callsign by the app's own rule
  (``tephra.feeds.adsb._callsign`` then ``tephra.models.is_airline_callsign``, copied
  below so this script needs nothing but the standard library), or when ``dbFlags & 1``;
- a kept target loses only ``r`` and ``dbFlags``. ``t`` stays, because the aircraft type
  drives fuel, exposure and the drafts.

Each changed file gets its new sha256 in the case's ``manifest.json`` (the replay source
checks every hash; file names keep their old prefix, which nothing reads), the answer's
``total`` is set to the targets left, and the manifest notes say the scrub ran. A file
whose bytes do not match the manifest, or whose layout is not adsb.lol's
one-target-per-line form, stops the run before anything is written.

The default is a dry run that only prints what would change; ``--write`` applies it.
The original files stay in git history until the publishing step filters them out.

    python3 scripts/scrub_adsb.py                 # dry run on java-live-20261010
    python3 scripts/scrub_adsb.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = PROJECT_ROOT / "data" / "replay" / "java-live-20261010"
ADSB_FEED = "adsb"
MILITARY_FLAG = 1
AIRLINE_CALLSIGN = re.compile(r"[A-Z]{3}[0-9][0-9A-Z]{0,3}")
"""Same pattern as ``tephra.models._AIRLINE_CALLSIGN``."""
SCRUBBED_KEYS = ("r", "dbFlags")
HEADER = '{"ac":['


class ScrubError(RuntimeError):
    pass


@dataclass
class FileChange:
    path: str
    old_sha256: str
    new_sha256: str
    new_bytes: bytes
    dropped: int
    scrubbed: int


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def callsign(flight: object, registration: object) -> str | None:
    """Trimmed callsign; None when it is just the registration (as the app reads it)."""
    sign = _text(flight)
    if sign is None:
        return None
    reg = (_text(registration) or "").replace("-", "").upper()
    return None if reg and sign.upper() == reg else sign


def is_airline(entry: dict[str, object]) -> bool:
    sign = callsign(entry.get("flight"), entry.get("r"))
    return bool(sign) and AIRLINE_CALLSIGN.fullmatch(sign or "") is not None


def is_military(entry: dict[str, object]) -> bool:
    flags = entry.get("dbFlags")
    return isinstance(flags, int) and not isinstance(flags, bool) and bool(flags & MILITARY_FLAG)


def _split(text: str, path: str) -> tuple[list[str], str]:
    """The target lines and the text after the target list, in adsb.lol's layout."""
    if not text.startswith(HEADER + "\n"):
        raise ScrubError(f"{path}: does not start with the adsb.lol target list")
    body = text[len(HEADER) + 1 :]
    end = body.find("\n]\n")
    if body.startswith("]\n"):
        return [], body[1:]
    if end < 0:
        raise ScrubError(f"{path}: target list has no closing line")
    lines = body[:end].split("\n")
    return lines, body[end + 2 :]


def scrub_text(text: str, path: str) -> tuple[str, int, int]:
    """New text, targets dropped and targets with fields removed."""
    payload = json.loads(text)
    lines, tail = _split(text, path)
    targets = payload.get("ac") or []
    if len(lines) != len(targets):
        raise ScrubError(f"{path}: {len(lines)} target lines but {len(targets)} targets")
    kept: list[str] = []
    dropped = scrubbed = 0
    for line in lines:
        entry = json.loads(line.removesuffix(","))
        if not isinstance(entry, dict):
            raise ScrubError(f"{path}: a target is not an object")
        if is_military(entry) or not is_airline(entry):
            dropped += 1
            continue
        if any(key in entry for key in SCRUBBED_KEYS):
            for key in SCRUBBED_KEYS:
                entry.pop(key, None)
            kept.append(json.dumps(entry, separators=(",", ":"), ensure_ascii=False))
            scrubbed += 1
        else:
            kept.append(line.removesuffix(","))
    if dropped == 0 and scrubbed == 0:
        return text, 0, 0
    if "total" in payload:
        tail = re.sub(r'(\n,"total": )\d+', rf"\g<1>{len(kept)}", tail, count=1)
    listed = ",\n".join(kept) + "\n" if kept else ""
    new_text = f"{HEADER}\n{listed}]{tail}"
    check = json.loads(new_text)
    if len(check.get("ac") or []) != len(kept):
        raise ScrubError(f"{path}: rewritten file does not hold the kept targets")
    return new_text, dropped, scrubbed


def plan(case_dir: Path, manifest: dict[str, Any]) -> list[FileChange]:
    records = manifest.get("records")
    if not isinstance(records, list):
        raise ScrubError("manifest has no records list")
    by_path: dict[str, str] = {}
    for record in records:
        if record.get("feed") != ADSB_FEED or record.get("status_code") != 200:
            continue
        path, sha = record["path"], record["sha256"]
        if by_path.setdefault(path, sha) != sha:
            raise ScrubError(f"{path}: manifest lists two hashes for one file")
    changes: list[FileChange] = []
    for path, sha in sorted(by_path.items()):
        raw = (case_dir / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ScrubError(f"{path}: bytes do not match the manifest sha256")
        new_text, dropped, scrubbed = scrub_text(raw.decode("utf-8"), path)
        if dropped == 0 and scrubbed == 0:
            continue
        new_bytes = new_text.encode("utf-8")
        changes.append(
            FileChange(
                path=path,
                old_sha256=sha,
                new_sha256=hashlib.sha256(new_bytes).hexdigest(),
                new_bytes=new_bytes,
                dropped=dropped,
                scrubbed=scrubbed,
            )
        )
    return changes


def apply(case_dir: Path, manifest: dict[str, Any], changes: list[FileChange]) -> None:
    new_hash = {change.path: change.new_sha256 for change in changes}
    for record in manifest["records"]:
        if record.get("feed") == ADSB_FEED and record.get("path") in new_hash:
            record["sha256"] = new_hash[record["path"]]
    today = datetime.now(UTC).date().isoformat()
    note = (
        f"Registrations and non-airline targets removed by scripts/scrub_adsb.py on {today}; "
        "original hashes in git history."
    )
    notes = manifest.get("notes")
    manifest["notes"] = f"{notes} {note}" if notes else note
    for change in changes:
        (case_dir / change.path).write_bytes(change.new_bytes)
    (case_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE, help="replay case directory")
    parser.add_argument("--write", action="store_true", help="apply the changes (default: dry run)")
    args = parser.parse_args(argv)
    case_dir: Path = args.case
    manifest = json.loads((case_dir / "manifest.json").read_text(encoding="utf-8"))
    try:
        changes = plan(case_dir, manifest)
    except ScrubError as exc:
        print(f"scrub refused, nothing written: {exc}", file=sys.stderr)
        return 1
    for change in changes:
        print(f"{change.path}: drop {change.dropped}, strip r/dbFlags from {change.scrubbed}")
    dropped = sum(change.dropped for change in changes)
    scrubbed = sum(change.scrubbed for change in changes)
    print(
        f"{len(changes)} files to change; {dropped} targets dropped; "
        f"{scrubbed} kept records lose r and dbFlags"
    )
    if not changes:
        return 0
    if not args.write:
        print("dry run: nothing written (pass --write to apply)")
        return 0
    apply(case_dir, manifest, changes)
    print(f"written: {len(changes)} files and {case_dir / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
