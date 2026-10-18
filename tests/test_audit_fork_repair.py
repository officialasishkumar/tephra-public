"""scripts/audit_fork_repair.py on an in-memory fake of the Firestore client, with the chain
written by the app's own store (``FirestoreStore``) and checked by the app's own walk
(``audit.verify_head``, what ``GET /api/audit/verify`` serves). The fork shapes are the live
chain's: a one-entry branch, a branch that went on for several seqs, and a fork where the entry
after it links to the second writer's branch."""

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from types import ModuleType
from typing import Any
from uuid import uuid4

import pytest
from test_store_namespace import FAKE_FIRESTORE, FakeDb, already_exists  # noqa: F401

from tephra.config import PROJECT_ROOT
from tephra.desk import audit
from tephra.desk.audit import ChainedAuditEntry, entry_digest
from tephra.models import AuditAction
from tephra.store.base import Collection
from tephra.store.firestore_store import DOC_FIELD, FirestoreStore
from tephra.util import timeutil


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "tephra_script_audit_fork_repair", PROJECT_ROOT / "scripts" / "audit_fork_repair.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


repair_script = _load_script()

T0 = datetime(2026, 9, 5, 11, 0, tzinfo=UTC)
CANDIDATE_CLOCK = datetime(2026, 9, 5, 10, 25, tzinfo=UTC)
"""A rollout candidate's replay clock starts at the loop's start"""


class Chain:
    """Entries written straight into the fake, so that forks can be laid out by hand."""

    def __init__(self) -> None:
        self.db = FakeDb()
        self.store = FirestoreStore.from_clients(FAKE_FIRESTORE, self.db, None, None)
        self.entries: list[ChainedAuditEntry] = []

    async def entry(
        self, after: ChainedAuditEntry | None, *, at: datetime, note: str
    ) -> ChainedAuditEntry:
        unsigned = ChainedAuditEntry(
            id=uuid4().hex,
            at=at,
            actor="system",
            action=AuditAction.AI_FAILED,
            note=note,
            seq=1 if after is None else after.seq + 1,
            prev_sha256=audit.GENESIS_SHA256 if after is None else after.sha256,
            sha256="",
        )
        entry = unsigned.model_copy(update={"sha256": entry_digest(unsigned)})
        await self.store.append_audit(entry)
        self.entries.append(entry)
        return entry

    async def run(
        self, after: ChainedAuditEntry | None, n: int, *, start: datetime, note: str
    ) -> list[ChainedAuditEntry]:
        written: list[ChainedAuditEntry] = []
        for i in range(n):
            after = await self.entry(
                after, at=start + timedelta(seconds=20 * i), note=f"{note} {i}"
            )
            written.append(after)
        return written

    def raw(self, entry: ChainedAuditEntry) -> dict[str, Any]:
        return dict(self.db.docs[(str(Collection.AUDIT), entry.id)])

    def archived(self) -> dict[str, dict[str, Any]]:
        return {
            path[1]: doc
            for path, doc in self.db.docs.items()
            if path[0] == audit.ARCHIVE_COLLECTION
        }

    async def verify(self) -> Any:
        """The app's own walk, on a fresh store object (a fresh process)."""
        return await audit.verify_head(
            FirestoreStore.from_clients(FAKE_FIRESTORE, self.db, None, None)
        )


def source(chain: Chain) -> Any:
    return repair_script.FirestoreAudit(FAKE_FIRESTORE, chain.db)


async def live_shapes(chain: Chain) -> dict[str, list[ChainedAuditEntry]]:
    """seq 1-4; a one-entry fork at 5; a run of forks at 8-10 where the second writer's branch
    went on for three entries; a fork at 13 that the entry after it continued on the second
    writer's side; then the chain goes on."""
    serving = await chain.run(None, 4, start=T0, note="serving")
    lone = await chain.entry(serving[-1], at=CANDIDATE_CLOCK, note="candidate startup tick")
    kept5 = await chain.entry(serving[-1], at=T0 + timedelta(seconds=80), note="serving 4")
    after5 = await chain.run(kept5, 2, start=T0 + timedelta(seconds=100), note="serving")
    kept_run = await chain.run(after5[-1], 3, start=T0 + timedelta(seconds=140), note="serving")
    dead_run = await chain.run(after5[-1], 3, start=CANDIDATE_CLOCK, note="candidate worker")
    after_run = await chain.run(kept_run[-1], 2, start=T0 + timedelta(seconds=200), note="serving")
    first_writer13 = await chain.entry(
        after_run[-1], at=T0 + timedelta(seconds=240), note="serving, never continued"
    )
    second_writer13 = await chain.entry(
        after_run[-1], at=CANDIDATE_CLOCK + timedelta(seconds=60), note="candidate"
    )
    tail = await chain.run(second_writer13, 3, start=T0 + timedelta(seconds=260), note="serving")
    return {
        "dead": [lone, *dead_run, first_writer13],
        "kept5": [kept5],
        "kept_run": kept_run,
        "second_writer13": [second_writer13],
        "tail": tail,
    }


@pytest.mark.usefixtures("already_exists")
async def test_the_live_fork_shapes_are_found_by_the_app_s_walk() -> None:
    chain = Chain()
    await live_shapes(chain)
    head = await chain.verify()
    assert head.intact is False
    assert head.problems == ["fork at seq 5", "fork at seq 8-10", "fork at seq 13"]
    forks, other = repair_script.forks_in_problems(head.problems)
    assert forks == [(5, 5), (8, 10), (13, 13)]
    assert other == []


@pytest.mark.usefixtures("already_exists")
async def test_a_dry_run_changes_nothing_and_says_which_branch_is_the_second_writer_s() -> None:
    chain = Chain()
    await live_shapes(chain)
    before = dict(chain.db.docs)
    outcome = await repair_script.repair(source(chain), [(5, 5), (8, 10), (13, 13)], apply=False)
    assert chain.db.docs == before, "a dry run writes and deletes nothing"
    assert outcome.moved == 0
    assert outcome.stopped == 0
    text = "\n".join(outcome.lines)
    assert text.count("second writer: the moved branch: its times do not fit") == 2
    assert "second writer: the KEPT branch" in text, "seq 13 continued on the candidate's side"
    assert text.count("dry run: --apply would move") == 3
    assert "candidate startup tick" in text


@pytest.mark.usefixtures("already_exists")
async def test_apply_moves_only_the_dead_branches_and_the_app_s_walk_passes() -> None:
    chain = Chain()
    shapes = await live_shapes(chain)
    total = len(chain.entries)
    originals = {entry.id: chain.raw(entry) for entry in shapes["dead"]}
    repaired_at = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)
    started = timeutil.SystemClock().now()
    reader = source(chain)
    outcome = await repair_script.repair(
        reader, [(5, 5), (8, 10), (13, 13)], apply=True, run_at=repaired_at
    )
    assert outcome.stopped == 0
    assert outcome.moved == len(shapes["dead"]) == 5

    head = await chain.verify()
    assert (head.intact, head.problems) == (True, [])
    assert head.entries == total - 5
    assert head.sha256 == shapes["tail"][-1].sha256, "the head is the one the app holds"
    for entry in [*shapes["kept5"], *shapes["kept_run"], *shapes["second_writer13"]]:
        assert (str(Collection.AUDIT), entry.id) in chain.db.docs, "kept entries are untouched"

    archived = chain.archived()
    assert set(archived) == set(originals)
    for doc_id, doc in archived.items():
        assert doc["original"] == originals[doc_id], "a verbatim copy, tephra_doc included"
        assert DOC_FIELD in doc["original"]
        assert doc["archived_at"] == "2026-10-18T09:00:00.000Z"
        assert "no later entry links to" in doc["reason"]
        assert (str(Collection.AUDIT), doc_id) not in chain.db.docs

    marker = await chain.store.get(Collection.RUNTIME, audit.REPAIR_DOC)
    assert marker is not None
    assert timeutil.parse_iso(marker["repaired_at"]) >= started, "taken after the last delete"
    assert marker["moved"] == 5
    assert marker["forks"] == ["seq 5", "seq 8-10", "seq 13"]


@pytest.mark.usefixtures("already_exists")
async def test_only_the_fork_s_range_is_read() -> None:
    chain = Chain()
    serving = await chain.run(None, 300, start=T0, note="serving")
    await chain.entry(serving[-1], at=CANDIDATE_CLOCK, note="candidate")
    kept = await chain.entry(serving[-1], at=T0 + timedelta(seconds=6000), note="serving")
    await chain.run(kept, 100, start=T0 + timedelta(seconds=6020), note="serving")
    reader = source(chain)
    chain.db.streamed = 0
    outcome = await repair_script.repair(reader, [(301, 301)], apply=True)
    assert outcome.moved == 1
    assert chain.db.streamed == 4 + 3, "seq 300-302 read to plan, and again to check"
    assert reader.reads <= 9, "plus the archived copy read back, never the whole collection"
    assert (await chain.verify()).intact is True


@pytest.mark.usefixtures("already_exists")
async def test_a_second_run_finds_nothing_to_do() -> None:
    chain = Chain()
    await live_shapes(chain)
    forks = [(5, 5), (8, 10), (13, 13)]
    await repair_script.repair(source(chain), forks, apply=True)
    after_first = dict(chain.db.docs)
    again = await repair_script.repair(source(chain), forks, apply=True)
    assert again.moved == 0
    assert again.stopped == 0
    assert "\n".join(again.lines).count("already repaired") == 3
    marker = (str(Collection.RUNTIME), audit.REPAIR_DOC)
    changed = {
        key
        for key in {*after_first, *chain.db.docs}
        if after_first.get(key) != chain.db.docs.get(key)
    }
    assert changed == {marker}, "no move, no delete: only the marker is written again"


@pytest.mark.usefixtures("already_exists")
async def test_a_run_cut_short_after_the_copy_finishes_on_the_next_run() -> None:
    chain = Chain()
    shapes = await live_shapes(chain)
    reader = source(chain)
    plan = await repair_script.plan_fork(reader, 5, 5)
    [lone] = plan.to_archive()
    await reader.archive(lone, {"reason": "copied by a run that stopped here"})
    assert (str(Collection.AUDIT), lone.doc_id) in chain.db.docs

    outcome = await repair_script.repair(source(chain), [(5, 5)], apply=True)
    assert outcome.moved == 1
    assert (str(Collection.AUDIT), shapes["dead"][0].id) not in chain.db.docs
    assert chain.archived()[lone.doc_id]["original"] == lone.raw


@pytest.mark.usefixtures("already_exists")
async def test_a_fork_at_the_newest_entry_is_left_alone() -> None:
    chain = Chain()
    serving = await chain.run(None, 3, start=T0, note="serving")
    await chain.entry(serving[-1], at=T0 + timedelta(minutes=1), note="serving")
    await chain.entry(serving[-1], at=CANDIDATE_CLOCK, note="candidate")
    before = dict(chain.db.docs)
    outcome = await repair_script.repair(source(chain), [(4, 4)], apply=True)
    assert outcome.stopped == 1
    assert outcome.moved == 0
    assert "fork reaches the newest entry" in "\n".join(outcome.lines)
    assert chain.db.docs == before


@pytest.mark.usefixtures("already_exists")
async def test_a_fork_that_cannot_be_made_whole_by_removing_a_branch_stops() -> None:
    chain = Chain()
    serving = await chain.run(None, 3, start=T0, note="serving")
    await chain.entry(serving[-1], at=T0 + timedelta(minutes=1), note="one")
    await chain.entry(serving[-1], at=T0 + timedelta(minutes=1), note="two")
    stray = ChainedAuditEntry(
        id="stray",
        at=T0 + timedelta(minutes=2),
        actor="system",
        action=AuditAction.AI_FAILED,
        note="links to neither branch",
        seq=5,
        prev_sha256="f" * 64,
        sha256="",
    )
    await chain.store.append_audit(stray.model_copy(update={"sha256": entry_digest(stray)}))
    before = dict(chain.db.docs)
    outcome = await repair_script.repair(source(chain), [(4, 4)], apply=True)
    assert outcome.stopped == 1
    text = "\n".join(outcome.lines)
    assert "STOP" in text
    assert "links to no single entry at seq 4" in text
    assert chain.db.docs == before, "no hash is rewritten and nothing moves"


def test_seqs_and_problem_lists_parse() -> None:
    assert repair_script.parse_seqs("5664-5668, 14370,29379") == [
        (5664, 5668),
        (14370, 14370),
        (29379, 29379),
    ]
    with pytest.raises(ValueError, match="not a seq range"):
        repair_script.parse_seqs("5668-5664")
    forks, other = repair_script.forks_in_problems(
        ["fork at seq 5664-5668", "fork at seq 14370", "broken link at seq 9"]
    )
    assert forks == [(5664, 5668), (14370, 14370)]
    assert other == ["broken link at seq 9"]


def test_no_token_no_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credentials come only from the token in the environment: without it the script stops
    before any Google client exists (Application Default Credentials are never consulted)."""
    monkeypatch.delenv(repair_script.TOKEN_ENV, raising=False)
    with pytest.raises(repair_script.NoToken, match="GOOGLE_OAUTH_ACCESS_TOKEN is not set"):
        repair_script.firestore_clients("regal-wall-392020", "(default)")
    assert repair_script.main(["--project", "regal-wall-392020", "--seqs", "5"]) == 2
    text = (PROJECT_ROOT / "scripts" / "audit_fork_repair.py").read_text()
    assert "google.auth.default" not in text
    assert "subprocess" not in text


@pytest.mark.usefixtures("already_exists")
async def test_a_store_without_the_asked_seqs_stops_and_changes_nothing() -> None:
    """A wrong --project or --database: an empty audit collection, or a shorter chain, is not
    "already repaired"."""
    for entries in (0, 6):
        chain = Chain()
        if entries:
            await chain.run(None, entries, start=T0, note="another chain")
        before = dict(chain.db.docs)
        chain.db.streamed = 0
        outcome = await repair_script.repair(
            source(chain), [(5664, 5668), (14370, 14370)], apply=True
        )
        assert outcome.stopped == 2
        assert outcome.moved == 0
        text = "\n".join(outcome.lines)
        assert "already repaired" not in text
        assert text.count("does not hold the chain named") == 2
        assert chain.db.docs == before, "nothing is written, the marker neither"
        assert chain.db.streamed == 0


@pytest.mark.usefixtures("already_exists")
async def test_a_run_that_failed_before_the_marker_is_marked_by_the_next() -> None:
    chain = Chain()
    await live_shapes(chain)
    forks = [(5, 5), (8, 10), (13, 13)]
    reader = source(chain)

    async def fails(doc: Any) -> None:
        raise RuntimeError("transient")

    reader.mark_repaired = fails
    with pytest.raises(RuntimeError, match="transient"):
        await repair_script.repair(reader, forks, apply=True)
    assert await chain.store.get(Collection.RUNTIME, audit.REPAIR_DOC) is None
    again = await repair_script.repair(source(chain), forks, apply=True)
    assert again.moved == 0
    marker = await chain.store.get(Collection.RUNTIME, audit.REPAIR_DOC)
    assert marker is not None
    assert marker["forks"] == ["seq 5", "seq 8-10", "seq 13"]


@pytest.mark.usefixtures("already_exists")
async def test_the_site_head_must_be_in_the_store() -> None:
    chain = Chain()
    shapes = await live_shapes(chain)
    newest = shapes["tail"][-1]
    same = repair_script.SiteHead(newest.seq, newest.sha256, [])
    assert await repair_script.same_chain(source(chain), same) is None
    other = repair_script.SiteHead(newest.seq, "e" * 64, [])
    assert "not the site's chain" in (await repair_script.same_chain(source(chain), other) or "")
    beyond = repair_script.SiteHead(newest.seq + 500, newest.sha256, [])
    assert await repair_script.same_chain(source(chain), beyond) is not None


@pytest.mark.usefixtures("already_exists")
async def test_a_dry_run_names_the_advisory_of_each_entry() -> None:
    chain = Chain()
    serving = await chain.run(None, 3, start=T0, note="serving")
    unsigned = ChainedAuditEntry(
        id=uuid4().hex,
        at=CANDIDATE_CLOCK,
        actor="system",
        action=AuditAction.SUPERSEDED,
        advisory_id="adv_0123456789ab",
        seq=4,
        prev_sha256=serving[-1].sha256,
        sha256="",
    )
    await chain.store.append_audit(unsigned.model_copy(update={"sha256": entry_digest(unsigned)}))
    kept = await chain.entry(serving[-1], at=T0 + timedelta(minutes=1), note="serving")
    await chain.entry(kept, at=T0 + timedelta(minutes=2), note="serving")
    outcome = await repair_script.repair(source(chain), [(4, 4)], apply=False)
    assert "SUPERSEDED advisory adv_0123456789ab" in "\n".join(outcome.lines)


@pytest.mark.usefixtures("already_exists")
async def test_full_on_an_intact_chain_is_success(monkeypatch: pytest.MonkeyPatch) -> None:
    chain = Chain()
    await chain.run(None, 5, start=T0, note="serving")
    monkeypatch.setattr(repair_script, "firestore_clients", lambda *_: (FAKE_FIRESTORE, chain.db))
    args = repair_script.parse_args(["--project", "p", "--full"])
    assert await repair_script.main_async(args) == 0
    assert await chain.store.get(Collection.RUNTIME, audit.REPAIR_DOC) is None, "dry run"
    args = repair_script.parse_args(["--project", "p", "--full", "--apply"])
    assert await repair_script.main_async(args) == 0
    assert await chain.store.get(Collection.RUNTIME, audit.REPAIR_DOC) is not None
