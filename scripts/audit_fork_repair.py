"""Repair forks in the live audit chain, in the open: dry run by default.

A fork is two entries at one ``seq`` that both link to the entry before it: two instances
appended after the same newest entry during a rollout. Each fork has one branch that later
entries link to and one (or more) that no later entry links to. Moving the dead branch out of
``audit`` leaves one entry per seq, every link intact, so the app's own walk
(``GET /api/audit/verify``) passes again with no hash rewritten. Nothing is lost: each moved
document goes verbatim (its stored fields, ``tephra_doc`` included) into
``audit_forks_archive`` with the reason and the time of the run, and it is deleted from
``audit`` only after its copy has been read back equal.

Only the seq ranges of the forks are read (Firestore bills a read per document): give them
with ``--seqs`` (as ``/api/state`` lists them, ``5664-5668,14370``) or let ``--site`` read them
from the service's public ``/api/state``. ``--full`` walks the whole collection instead (one
read per entry). Before anything else the store must hold the chain named: every asked seq has
an entry, and with ``--site`` the entry at the site's head seq carries the site's head hash (a
wrong ``--project`` or ``--database`` stops here). With ``--apply`` the dead branches are moved,
each range is read again and walked, and once every fork named walks whole (moved in this run
or an earlier one) ``runtime/audit_repair`` is written with the time after the last delete, so
the serving instance walks its chain again at its next checkpoint (within five minutes). A
second ``--apply`` moves nothing and writes only that marker again.

Credentials come only from an OAuth access token in ``GOOGLE_OAUTH_ACCESS_TOKEN`` (for example
one the owner printed in their own gcloud configuration); Application Default Credentials are
never read and this script never runs gcloud.

    GOOGLE_OAUTH_ACCESS_TOKEN=... uv run --extra gcp python scripts/audit_fork_repair.py \\
        --project regal-wall-392020 --site https://tephra-647733667799.asia-southeast1.run.app
    ... --seqs 5664-5668,14370 --apply

Exit status: 0 when every fork named was repaired, or is already, or (dry run) can be, and
when ``--full`` finds no fork; 1 when a fork cannot be repaired without rewriting a hash, or the
store does not hold the chain named (nothing is changed for it); 2 on bad input (no token
included); 3 when Firestore or the site refused or failed a call (the run stops there).
"""

import argparse
import asyncio
import json
import os
import re
import sys
import urllib.request
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Protocol

from pydantic import ValidationError

from tephra.desk.audit import (
    ARCHIVE_COLLECTION,
    GENESIS_SHA256,
    REPAIR_DOC,
    ChainedAuditEntry,
    _walk,
)
from tephra.models import ChainHead
from tephra.store import decode_doc
from tephra.store.base import Collection, escape_doc_id
from tephra.store.firestore_store import DOC_FIELD, FirestoreStore
from tephra.util import timeutil

TOKEN_ENV: Final = "GOOGLE_OAUTH_ACCESS_TOKEN"
WIDEN_LIMIT: Final = 50
"""Seqs a window may grow on either side to reach single entries"""
NEIGHBOUR_SLACK_S: Final = 120
"""Seconds a branch's times may lie outside its neighbours' and still fit between them"""
FORK_PROBLEM: Final = re.compile(r"^fork at seq (\d+)(?:-(\d+))?$")
TOOL: Final = "scripts/audit_fork_repair.py"
GOOGLE_ERRORS: Final = ("google.api_core.", "google.auth.")
"""Modules of the client's errors (a refused token, a missing database): exit 3, no traceback"""


# --- what is read ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stored:
    """One audit document: its fields as Firestore holds them and the entry they carry."""

    raw: dict[str, Any]
    entry: ChainedAuditEntry

    @property
    def doc_id(self) -> str:
        return escape_doc_id(self.entry.id)


def stored(raw: Mapping[str, Any]) -> Stored:
    text = raw.get(DOC_FIELD)
    if not isinstance(text, str):
        raise ValueError(f"an audit document without {DOC_FIELD}")
    return Stored(dict(raw), ChainedAuditEntry.model_validate(decode_doc(text)))


class AuditSource(Protocol):
    async def read_range(self, lo: int, hi: int) -> list[Stored]:
        """Entries with ``lo <= seq <= hi``, by seq."""
        ...

    async def read_all(self) -> list[Stored]: ...

    async def archive(self, item: Stored, meta: Mapping[str, Any]) -> None:
        """Copy ``item`` into the archive (kept when an equal copy is already there)."""
        ...

    async def archived_copy(self, doc_id: str) -> dict[str, Any] | None: ...

    async def delete(self, doc_id: str) -> None: ...

    async def mark_repaired(self, doc: Mapping[str, Any]) -> None: ...


class FirestoreAudit:
    """The root ``audit`` collection through the Firestore client's own calls."""

    def __init__(self, firestore: Any, db: Any) -> None:
        self._firestore = firestore
        self._db = db
        self.reads = 0
        self.writes = 0
        self.deletes = 0

    async def read_range(self, lo: int, hi: int) -> list[Stored]:
        field_filter = self._firestore.FieldFilter
        query = (
            self._db.collection(str(Collection.AUDIT))
            .where(filter=field_filter("seq", ">", lo - 1))
            .where(filter=field_filter("seq", "<", hi + 1))
            .order_by("seq", direction=self._firestore.Query.ASCENDING)
        )
        return await self._stream(query)

    async def read_all(self) -> list[Stored]:
        query = self._db.collection(str(Collection.AUDIT)).order_by(
            "seq", direction=self._firestore.Query.ASCENDING
        )
        return await self._stream(query)

    async def _stream(self, query: Any) -> list[Stored]:
        found: list[Stored] = []
        async for snapshot in query.stream():
            self.reads += 1
            found.append(stored(snapshot.to_dict() or {}))
        return sorted(found, key=lambda item: item.entry.seq)

    async def archive(self, item: Stored, meta: Mapping[str, Any]) -> None:
        ref = self._db.collection(ARCHIVE_COLLECTION).document(item.doc_id)
        held = await self.archived_copy(item.doc_id)
        if held is not None and held == item.raw:
            return
        await ref.set({**meta, "original": item.raw})
        self.writes += 1

    async def archived_copy(self, doc_id: str) -> dict[str, Any] | None:
        snapshot = await self._db.collection(ARCHIVE_COLLECTION).document(doc_id).get()
        self.reads += 1
        if not snapshot.exists:
            return None
        original = (snapshot.to_dict() or {}).get("original")
        return dict(original) if isinstance(original, Mapping) else None

    async def delete(self, doc_id: str) -> None:
        await self._db.collection(str(Collection.AUDIT)).document(doc_id).delete()
        self.deletes += 1

    async def mark_repaired(self, doc: Mapping[str, Any]) -> None:
        store = FirestoreStore.from_clients(
            self._firestore, self._db, None, None, owns_clients=False
        )
        await store.put(Collection.RUNTIME, REPAIR_DOC, doc)
        self.writes += 1


# --- the plan for one fork --------------------------------------------------------------------


@dataclass
class Branch:
    """Entries at the fork's seqs, linked one to the next."""

    entries: list[Stored]

    @property
    def first_seq(self) -> int:
        return self.entries[0].entry.seq

    @property
    def last_seq(self) -> int:
        return self.entries[-1].entry.seq


@dataclass
class ForkPlan:
    asked: tuple[int, int]
    window: tuple[int, int] | None = None
    fork_seqs: list[int] = field(default_factory=list)
    parent: Stored | None = None
    continuation: Stored | None = None
    kept: Branch | None = None
    dead: list[Branch] = field(default_factory=list)
    second_writer: str = ""
    """Which branch is the second writer's, and why"""
    stop: str | None = None
    """Why nothing may be moved for this fork"""

    @property
    def label(self) -> str:
        first, last = self.asked
        return f"seq {first}" if first == last else f"seq {first}-{last}"

    def to_archive(self) -> list[Stored]:
        return [item for branch in self.dead for item in branch.entries]


def parse_seqs(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for part in (p.strip() for p in text.split(",")):
        if not part:
            continue
        match = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if match is None:
            raise ValueError(f"not a seq or a seq range: {part!r}")
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first:
            raise ValueError(f"not a seq range: {part!r}")
        ranges.append((first, last))
    return ranges


def forks_in_problems(problems: Sequence[str]) -> tuple[list[tuple[int, int]], list[str]]:
    """The fork ranges a walk listed, and its other problems (which this script leaves)."""
    forks: list[tuple[int, int]] = []
    other: list[str] = []
    for problem in problems:
        match = FORK_PROBLEM.match(problem)
        if match is None:
            other.append(problem)
            continue
        first = int(match.group(1))
        forks.append((first, int(match.group(2) or first)))
    return forks, other


async def plan_fork(source: AuditSource, first: int, last: int) -> ForkPlan:
    """Read the fork's seqs and one seq on either side (more while those are forked too) and
    work out the branch later entries link to; the rest is what may move."""
    plan = ForkPlan(asked=(first, last))
    lo, hi = max(1, first - 1), last + 1
    items = await source.read_range(lo, hi)
    absent = [seq for seq in range(first, last + 1) if seq not in _by_seq(items)]
    if absent:
        plan.window = (lo, hi)
        plan.stop = (
            f"no entry at seq {absent[0]}: this store does not hold the chain named "
            "(check --project and --database)"
        )
        return plan
    for _ in range(WIDEN_LIMIT):
        by_seq = _by_seq(items)
        widen_lo = lo > 1 and len(by_seq.get(lo, [])) > 1
        widen_hi = len(by_seq.get(hi, [])) > 1
        if not (widen_lo or widen_hi):
            break
        if widen_lo:
            lo -= 1
            items = [*await source.read_range(lo, lo), *items]
        if widen_hi:
            hi += 1
            items = [*items, *await source.read_range(hi, hi)]
    by_seq = _by_seq(items)
    plan.window = (lo, hi)
    plan.fork_seqs = sorted(seq for seq, here in by_seq.items() if len(here) > 1)
    if not plan.fork_seqs:
        return plan  # already repaired (or never forked): nothing to move
    end = by_seq.get(hi, [])
    if len(end) != 1:
        plan.stop = (
            f"seq {hi} has {len(end)} entries: the fork reaches the newest entry, so no later "
            "entry says which branch the chain goes on from"
        )
        return plan
    missing = [seq for seq in range(lo, hi) if seq not in by_seq]
    if missing:
        plan.stop = f"no entry at seq {missing[0]}: a gap, not a fork"
        return plan
    plan.continuation = end[0]
    plan.parent = by_seq[lo][0] if len(by_seq[lo]) == 1 else None
    path = [plan.continuation]
    while path[-1].entry.seq > lo:
        child = path[-1]
        parents = [
            item
            for item in by_seq[child.entry.seq - 1]
            if item.entry.sha256 == child.entry.prev_sha256
        ]
        if len(parents) != 1:
            plan.stop = (
                f"seq {child.entry.seq} ({child.entry.id}) links to no single entry at seq "
                f"{child.entry.seq - 1}: removing a branch cannot make the chain whole"
            )
            return plan
        path.append(parents[0])
    path.reverse()
    on_path = {item.entry.id for item in path}
    kept = [item for item in path if item.entry.seq in plan.fork_seqs]
    plan.kept = Branch(kept)
    dead = [item for item in items if item.entry.id not in on_path]
    plan.dead = _branches(dead)
    if lo == 1 and path[0].entry.prev_sha256 != GENESIS_SHA256:
        plan.stop = "the first entry does not start from the genesis hash"
        return plan
    check = _walk_from(path)
    if not check.intact:
        plan.stop = "without the dead branches the range still walks with problems: " + "; ".join(
            check.problems[:3]
        )
        return plan
    plan.second_writer = _second_writer(plan)
    return plan


def _entry_doc(item: Stored) -> dict[str, Any]:
    return item.entry.model_dump(mode="json")


def _walk_from(items: Sequence[Stored]) -> ChainHead:
    """The app's walk over ``items`` (by seq), starting from the link the first one names:
    every entry's own hash and every link inside the range are checked."""
    first = items[0].entry
    return _walk(
        [_entry_doc(item) for item in items],
        start_seq=first.seq - 1,
        start_sha256=first.prev_sha256,
    )


def _by_seq(items: Sequence[Stored]) -> dict[int, list[Stored]]:
    found: dict[int, list[Stored]] = {}
    seen: set[str] = set()
    for item in items:
        if item.entry.id in seen:
            continue
        seen.add(item.entry.id)
        found.setdefault(item.entry.seq, []).append(item)
    return found


def _branches(dead: Sequence[Stored]) -> list[Branch]:
    """Group the dead entries into runs that link one to the next."""
    branches: list[Branch] = []
    for item in sorted(dead, key=lambda d: (d.entry.seq, d.entry.at, d.entry.id)):
        for branch in branches:
            tail = branch.entries[-1].entry
            if tail.seq + 1 == item.entry.seq and tail.sha256 == item.entry.prev_sha256:
                branch.entries.append(item)
                break
        else:
            branches.append(Branch([item]))
    return branches


def _fits(branch: Branch, start: datetime, end: datetime) -> bool:
    slack = NEIGHBOUR_SLACK_S
    return all(
        (start - item.entry.at).total_seconds() <= slack
        and (item.entry.at - end).total_seconds() <= slack
        for item in branch.entries
    )


def _second_writer(plan: ForkPlan) -> str:
    """Entries carry no instance id, but each carries the time of the clock that wrote it (the
    replay clock in REPLAY): the serving instance's fit between the entries before and after
    the fork; a rollout candidate's run on a clock of its own (its replay restarts at the
    loop's start), so they do not."""
    if plan.parent is None or plan.continuation is None or plan.kept is None:
        return "undetermined: the fork starts at the first entry"
    start, end = plan.parent.entry.at, plan.continuation.entry.at
    span = f"{timeutil.to_iso(start)} .. {timeutil.to_iso(end)}"
    kept_fits = _fits(plan.kept, start, end)
    dead_fit = [_fits(branch, start, end) for branch in plan.dead]
    if kept_fits and not any(dead_fit):
        return (
            "the moved branch: its times do not fit between its neighbours "
            f"({span}) while the kept branch's do, so another clock wrote it"
        )
    if not kept_fits and all(dead_fit):
        return (
            "the KEPT branch: its times do not fit between its neighbours "
            f"({span}) while the moved branch's do; the moved branch is still the only one "
            "that can go without breaking the link of the entry after the fork"
        )
    return (
        f"undetermined: the times of both branches {'fit' if kept_fits else 'do not fit'} "
        f"between the neighbours ({span}); the moved branch is the one no later entry links to"
    )


# --- printing -------------------------------------------------------------------------------


def _line(item: Stored) -> str:
    entry = item.entry
    note = (entry.note or "")[:70]
    advisory = f" advisory {entry.advisory_id}" if entry.advisory_id else ""
    return (
        f"      seq {entry.seq} id {entry.id} {entry.action.value}{advisory} at "
        f"{timeutil.to_iso(entry.at)} by {entry.actor}" + (f": {note}" if note else "")
    )


def describe(plan: ForkPlan) -> list[str]:
    lines = [f"fork at {plan.label} (read seq {plan.window[0]}-{plan.window[1]})"]
    if not plan.fork_seqs and plan.stop is None:
        lines.append("  already repaired: one entry per seq here")
        return lines
    if plan.fork_seqs:
        lines.append(f"  forked seqs now: {', '.join(map(str, plan.fork_seqs))}")
    if plan.parent is not None:
        lines.append("  before:")
        lines.append(_line(plan.parent))
    if plan.kept is not None:
        lines.append("  kept branch (the entry after the fork links to it):")
        lines.extend(_line(item) for item in plan.kept.entries)
    for n, branch in enumerate(plan.dead, 1):
        lines.append(f"  branch to move {n} (no later entry links to it):")
        lines.extend(_line(item) for item in branch.entries)
    if plan.continuation is not None:
        lines.append("  after:")
        lines.append(_line(plan.continuation))
    if plan.stop is not None:
        lines.append(f"  STOP: {plan.stop}; nothing is changed for this fork")
    else:
        lines.append(f"  second writer: {plan.second_writer}")
    return lines


# --- applying -------------------------------------------------------------------------------


async def apply_plan(source: AuditSource, plan: ForkPlan, *, run_id: str, run_at: str) -> int:
    """Copy each dead entry into the archive, read the copy back, then delete the original.
    Returns how many moved; raises when a copy does not read back equal (nothing of that
    entry is deleted)."""
    moved = 0
    kept_ids = [item.entry.id for item in plan.kept.entries] if plan.kept else []
    for item in plan.to_archive():
        meta = {
            "doc_id": item.doc_id,
            "collection": str(Collection.AUDIT),
            "seq": item.entry.seq,
            "fork": plan.label,
            "kept_ids": kept_ids,
            "reason": (
                f"fork at {plan.label}: a second branch at seq {item.entry.seq} that no later "
                "entry links to; moved here verbatim so the chain walks intact without "
                "rewriting any hash"
            ),
            "second_writer": plan.second_writer,
            "archived_at": run_at,
            "run_id": run_id,
            "tool": TOOL,
        }
        await source.archive(item, meta)
        copy = await source.archived_copy(item.doc_id)
        if copy != item.raw:
            raise RuntimeError(f"the archived copy of {item.doc_id} does not read back equal")
        await source.delete(item.doc_id)
        moved += 1
    return moved


async def check_window(source: AuditSource, plan: ForkPlan) -> str | None:
    """Read the repaired range again and walk it from the entry before it; None when whole."""
    assert plan.window is not None
    lo, hi = plan.window
    items = sorted(await source.read_range(lo, hi), key=lambda item: item.entry.seq)
    if not items:
        return "the range reads empty"
    walk = _walk_from(items)
    if not walk.intact:
        return "; ".join(walk.problems[:3])
    if len({item.entry.seq for item in items}) != len(items):
        return "a seq still has more than one entry"
    return None


@dataclass
class Outcome:
    lines: list[str] = field(default_factory=list)
    moved: int = 0
    stopped: int = 0


async def repair(
    source: AuditSource,
    forks: Sequence[tuple[int, int]],
    *,
    apply: bool,
    run_at: datetime | None = None,
) -> Outcome:
    outcome = Outcome()
    run_id = uuid.uuid4().hex
    at = timeutil.to_iso(run_at or timeutil.SystemClock().now())
    repaired: list[str] = []
    for first, last in forks:
        plan = await plan_fork(source, first, last)
        outcome.lines.extend(describe(plan))
        if plan.stop is not None:
            outcome.stopped += 1
            continue
        if not plan.to_archive():
            if apply:
                problem = await check_window(source, plan)
                if problem is None:
                    repaired.append(plan.label)
                else:
                    outcome.stopped += 1
                    outcome.lines.append(f"  STOP: read again, the range has problems: {problem}")
            continue
        if not apply:
            outcome.lines.append(
                f"  dry run: --apply would move {len(plan.to_archive())} document(s) to "
                f"{ARCHIVE_COLLECTION}"
            )
            continue
        moved = await apply_plan(source, plan, run_id=run_id, run_at=at)
        outcome.moved += moved
        problem = await check_window(source, plan)
        if problem is None:
            repaired.append(plan.label)
            lo, hi = plan.window or plan.asked
            outcome.lines.append(f"  moved {moved}; seq {lo}-{hi} read again: walks whole")
        else:
            outcome.stopped += 1
            outcome.lines.append(f"  moved {moved}; the range still has problems: {problem}")
    if apply and forks and not outcome.stopped:
        await mark(source, run_id=run_id, forks=repaired, moved=outcome.moved, lines=outcome.lines)
    return outcome


async def mark(
    source: AuditSource, *, run_id: str, forks: Sequence[str], moved: int, lines: list[str]
) -> None:
    """Write ``runtime/audit_repair`` with the time now, after the last delete: a walk the
    serving instance made while the run was moving entries is older than it, so that instance
    walks again. Written by every ``--apply`` that leaves each fork named whole, a re-run too,
    so a run that moved everything but failed before this write is finished by the next."""
    repaired_at = timeutil.to_iso(timeutil.SystemClock().now())
    await source.mark_repaired(
        {"repaired_at": repaired_at, "run_id": run_id, "forks": list(forks), "moved": moved}
    )
    lines.append(
        f"wrote runtime/{REPAIR_DOC}: the serving instance walks its chain again at its "
        "next checkpoint"
    )


async def full_walk(source: AuditSource) -> tuple[list[str], int]:
    items = await source.read_all()
    head = _walk([_entry_doc(item) for item in items])
    return head.problems, len(items)


# --- the command ------------------------------------------------------------------------------


@dataclass(frozen=True)
class SiteHead:
    """The audit head the site serves in ``/api/state``."""

    seq: int
    sha256: str
    problems: list[str]


def site_head(base: str) -> SiteHead:
    if not base.startswith("https://"):
        raise ValueError("--site must be an https:// URL")
    request = urllib.request.Request(
        base.rstrip("/") + "/api/state", headers={"User-Agent": "tephra-audit-fork-repair"}
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        state = json.load(response)
    audit = state.get("audit") or {}
    seq, sha256 = audit.get("seq"), audit.get("sha256")
    if not (isinstance(seq, int) and isinstance(sha256, str)):
        raise ValueError(f"{base}/api/state carries no audit head")
    return SiteHead(seq, sha256, [str(problem) for problem in audit.get("problems") or []])


async def same_chain(source: AuditSource, head: SiteHead) -> str | None:
    """None when the store holds the site's head entry (its seq with its hash): the project
    and database given are the site's. Otherwise why not."""
    here = await source.read_range(head.seq, head.seq)
    if any(item.entry.sha256 == head.sha256 for item in here):
        return None
    return (
        f"this store has no entry at seq {head.seq} with the site's head hash "
        f"{head.sha256[:12]}...: it is not the site's chain (check --project and --database)"
    )


class NoToken(Exception):
    """No access token in the environment: bad input (exit 2), before any Google import."""


def firestore_clients(project: str, database: str) -> tuple[Any, Any]:
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        raise NoToken(
            f"{TOKEN_ENV} is not set: put an OAuth access token there (this script never reads "
            "Application Default Credentials and never runs gcloud)"
        )
    from google.cloud import firestore
    from google.oauth2.credentials import Credentials

    client = firestore.AsyncClient(
        project=project, database=database, credentials=Credentials(token)
    )
    return firestore, client


async def main_async(args: argparse.Namespace) -> int:
    try:
        forks = parse_seqs(args.seqs) if args.seqs else []
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not (forks or args.site or args.full):
        print("no fork named: give --seqs, --site or --full", file=sys.stderr)
        return 2
    head: SiteHead | None = None
    if args.site:
        try:
            head = site_head(args.site)
        except (OSError, ValueError) as exc:
            print(f"reading {args.site}/api/state failed: {exc}", file=sys.stderr)
            return 2 if isinstance(exc, ValueError) else 3
        found, other = forks_in_problems(head.problems)
        forks = [*forks, *found]
        print(f"{args.site}/api/state: head seq {head.seq}, lists {len(found)} fork(s)")
        for problem in other:
            print(f"  not a fork, left alone: {problem}")
    try:
        firestore, db = firestore_clients(args.project, args.database)
    except NoToken as exc:
        print(exc, file=sys.stderr)
        return 2
    source = FirestoreAudit(firestore, db)
    try:
        return await _run(source, args, forks, head)
    except Exception as exc:
        if not type(exc).__module__.startswith(GOOGLE_ERRORS):
            raise
        print(f"Firestore refused or failed a call: {exc}", file=sys.stderr)
        print(
            f"Firestore so far: {source.reads} read(s), {source.writes} write(s), "
            f"{source.deletes} delete(s)",
            file=sys.stderr,
        )
        return 3
    finally:
        closed = db.close()
        if asyncio.iscoroutine(closed):
            await closed


async def _run(
    source: "FirestoreAudit",
    args: argparse.Namespace,
    forks: list[tuple[int, int]],
    head: SiteHead | None,
) -> int:
    if head is not None:
        mismatch = await same_chain(source, head)
        if mismatch is not None:
            print(f"STOP: {mismatch}; nothing is changed")
            return 1
    intact_whole = False
    if args.full:
        problems, count = await full_walk(source)
        print(f"full walk: {count} entries, {len(problems)} problem(s)")
        found, rest = forks_in_problems(problems)
        forks = [*forks, *found]
        for problem in rest:
            print(f"  not a fork, left alone: {problem}")
        intact_whole = not problems
    if not forks:
        print("no fork to repair" + (": the whole chain walks intact" if intact_whole else ""))
        if args.apply and intact_whole:
            lines: list[str] = []
            await mark(source, run_id=uuid.uuid4().hex, forks=[], moved=0, lines=lines)
            print(*lines, sep="\n")
        return 0 if intact_whole or not args.full else 1
    outcome = await repair(source, sorted(set(forks)), apply=args.apply)
    for line in outcome.lines:
        print(line)
    if args.apply and args.full:
        problems, count = await full_walk(source)
        verdict = "intact" if not problems else "; ".join(problems[:5])
        print(f"full walk after the repair: {count} entries, {verdict}")
    print(
        f"Firestore: {source.reads} read(s), {source.writes} write(s), "
        f"{source.deletes} delete(s)" + ("" if args.apply else " (dry run: nothing changed)")
    )
    return 1 if outcome.stopped else 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--project", required=True, help="the Google Cloud project id")
    parser.add_argument("--database", default="(default)", help="the Firestore database")
    parser.add_argument("--seqs", help="fork seqs or ranges, e.g. 5664-5668,14370")
    parser.add_argument("--site", help="read the forks from <site>/api/state (public)")
    parser.add_argument("--full", action="store_true", help="walk the whole collection")
    parser.add_argument("--apply", action="store_true", help="move the dead branches")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return asyncio.run(main_async(parse_args(argv)))
    except ValidationError as exc:
        print(f"an audit document does not read as a chained entry: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
