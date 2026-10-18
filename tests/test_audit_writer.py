"""One writer for the audit chain across a rollout: two runtimes on one store file, as a
serving instance and a deploy's no-traffic candidate are on one Firestore database.

A candidate stands by (``Runtime.stand_by``): its startup tick builds the picture and appends
nothing, checkpoints nothing and runs no AI work, until its first Scheduler tick (or the first
request that records something) claims ``runtime/writer``. From that claim on, the old instance
appends nothing (``audit.gate`` reads the claim before every append). Also here: AI failures
audited once per flight, stage, reason and quota day; the start that walks only past the
verified point; and the re-walk a fork repair asks for."""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient
from test_api import DISPATCHER, PIN, FakeRuntime
from test_pipeline import (
    AT,
    DATA_DIR,
    FixtureSource,
    make_runtime,
    make_settings,
    tick_and_work,
)

from tephra.api.server import HANDED_OVER_RETRY_S, create_app
from tephra.config import Settings
from tephra.desk import audit, failures
from tephra.desk.approvals import SYSTEM_ACTOR, list_advisories
from tephra.desk.failures import NEWER_FAILURE, close_failure, list_failures, record_failure
from tephra.models import AdvisoryStatus, AiFailure, AuditAction, RunMode, SseEvent
from tephra.pipeline import AUDIT_HEAD_DOC, WRITER_DOC, Runtime, create_runtime
from tephra.store import open_store
from tephra.store.base import Collection, Store
from tephra.store.sqlite_store import SqliteStore
from tephra.util import timeutil
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock


@pytest.fixture(autouse=True)
def clock() -> Iterator[FixedClock]:
    fixed = FixedClock(AT)
    with use_clock(fixed):
        yield fixed


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


def instance(settings: Settings) -> Runtime:
    """A process on the shared store file, wired as ``create_runtime`` wires one under Cloud
    Scheduler: its own store object, the audit gate, standing by."""
    runtime = make_runtime(settings, FixtureSource())
    audit.gate(runtime.store, runtime.may_append, ask=runtime.may_write)
    runtime.stand_by()
    return runtime


@pytest.fixture
async def pair(settings: Settings) -> AsyncIterator[tuple[Runtime, Runtime]]:
    serving, candidate = instance(settings), instance(settings)
    yield serving, candidate
    for runtime in (serving, candidate):
        runtime.retired = True  # each test's end is no checkpoint of its own
        await runtime.aclose()


async def entries(settings: Settings) -> list[audit.ChainedAuditEntry]:
    reader = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    try:
        docs = await reader.list_docs(
            Collection.AUDIT, limit=audit.WALK_LIMIT, order_by="seq", descending=False
        )
    finally:
        await reader.aclose()
    return [audit.ChainedAuditEntry.model_validate(doc) for doc in docs]


async def problems(settings: Settings) -> list[str]:
    reader = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    try:
        return await audit.verify_chain(reader)
    finally:
        await reader.aclose()


async def writer(runtime: Runtime) -> str | None:
    doc = await runtime.store.get(Collection.RUNTIME, WRITER_DOC)
    return None if doc is None else doc["instance"]


async def note(runtime: Runtime, text: str) -> audit.AuditEntry:
    """An append as a request makes one (a Desk login, a visitor entering)."""
    return await audit.record(
        runtime.store, actor="desk:visitor", action=AuditAction.LOGIN_OK, note=text
    )


async def a_moment() -> None:
    """Claims are compared by wall-clock time at millisecond precision."""
    await asyncio.sleep(0.005)


# --- a simulated deploy --------------------------------------------------------------------------


async def test_a_deploy_leaves_one_chain_with_no_fork(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    serving, candidate = pair
    await serving.restore()
    await tick_and_work(serving, reason="scheduler")
    assert serving.standing_by is False
    assert await writer(serving) == serving.instance_id
    drafts = await list_advisories(serving.store, status=AdvisoryStatus.DRAFT)
    assert drafts, "the serving instance drafted"
    written = len(await entries(settings))
    assert written > 0
    state_before = await serving.store.get(Collection.RUNTIME, "state")

    # The deploy: a candidate starts on the same store and runs its startup tick.
    await a_moment()
    await candidate.restore()
    report = await tick_and_work(candidate, reason="startup")
    assert candidate.standing_by is True
    assert candidate.retired is True
    assert not report.skipped
    assert candidate.cones, "the candidate built its picture"
    assert candidate.bus.last(SseEvent.STATE) is not None, "and published it"
    assert len(await entries(settings)) == written, "the candidate appended nothing"
    assert await writer(serving) == serving.instance_id, "and claimed nothing"
    assert await serving.store.get(Collection.RUNTIME, "state") == state_before, "no checkpoint"
    assert [d.id for d in await list_advisories(serving.store, status=AdvisoryStatus.DRAFT)] == [
        d.id for d in drafts
    ], "the serving instance's drafts are untouched"

    # The serving instance goes on while the candidate is tested.
    await note(serving, "serving, during the candidate's smoke test")
    await tick_and_work(serving, reason="scheduler")

    # Traffic moves: the candidate's first Scheduler tick claims the writer.
    await a_moment()
    await tick_and_work(candidate, reason="scheduler")
    assert candidate.standing_by is False
    assert await writer(candidate) == candidate.instance_id

    # The old instance's work in flight appends nothing from that moment on.
    with pytest.raises(audit.NotWriter):
        await note(serving, "an old instance's late append")
    assert serving.retired is True
    assert await serving.worker.work_once(serving.worker._report()) is False

    for n in range(3):
        await note(candidate, f"the new serving instance {n}")
    chain = await entries(settings)
    assert [entry.seq for entry in chain] == list(range(1, len(chain) + 1)), "one entry a seq"
    assert await problems(settings) == []
    assert not any(entry.note == "an old instance's late append" for entry in chain)


async def test_two_writers_interleaving_after_the_claim_never_fork(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    old, new = pair
    await old.restore()
    await old.claim_writer()
    await note(old, "old 0")
    await a_moment()
    await new.restore()
    await new.claim_writer()
    refused = 0
    for n in range(5):
        try:
            await note(old, f"old {n + 1}")
        except audit.NotWriter:
            refused += 1
        await note(new, f"new {n}")
    assert refused == 5
    assert await problems(settings) == []
    assert [entry.note for entry in await entries(settings)] == [
        "old 0",
        *(f"new {n}" for n in range(5)),
    ]


async def test_a_request_on_a_standing_by_instance_claims_the_writer(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    """A restarted instance serves at once; the first request that records something proves
    it serves, so it claims rather than waiting up to a minute for the Scheduler."""
    serving, fresh = pair
    await serving.restore()
    await serving.claim_writer()
    await a_moment()
    await fresh.restore()
    assert fresh.standing_by is True
    await note(fresh, "a visitor entered on the new instance")
    assert fresh.standing_by is False
    assert await writer(fresh) == fresh.instance_id
    with pytest.raises(audit.NotWriter):
        await note(serving, "late")
    assert await problems(settings) == []


async def test_asking_a_standing_by_instance_whether_it_may_write_claims_nothing(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    """Review, item 1: WriterGuardMiddleware asks before auth, CSRF and routing, so an
    anonymous POST to a candidate's tag URL (even to a 404) must not take the writer."""
    serving, candidate = pair
    await serving.restore()
    await serving.claim_writer()
    await a_moment()
    await candidate.restore()
    for _ in range(3):
        assert await audit.writable(candidate.store) is True, "its append will claim"
    assert candidate.standing_by is True
    assert await writer(candidate) == serving.instance_id
    assert await audit.writable(serving.store) is True
    await note(serving, "the serving instance goes on")
    assert serving.retired is False


async def test_an_out_claimed_instance_stores_nothing_it_cannot_audit(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    """Review, item 2: a background run on the old instance that finishes after the new one
    claimed stores no draft, superseded draft or failure without its audit entry."""
    old, new = pair
    await old.restore()
    await old.claim_writer()
    await a_moment()
    await new.restore()
    await new.claim_writer()
    with pytest.raises(audit.NotWriter):
        await record_failure(old.store, old.bus, failure("LATE"))
    assert await list_failures(new.store, open_only=False, limit=10) == []
    assert old.retired is True
    assert await old.worker.work_once(old.worker._report()) is False
    assert await entries(settings) == []


async def test_a_standing_by_instance_resumes_a_stored_replay_without_writing(
    tmp_path: Path,
) -> None:
    """Review, item 4: restoring the Desk's replay choice at start would append MODE_SWITCH
    (claiming the writer, beside the serving instance's chain) and rewrite runtime/state."""
    settings = make_settings(tmp_path, data_dir=DATA_DIR)
    serving, candidate = instance(settings), instance(settings)
    try:
        await serving.claim_writer()
        state = {"mode": RunMode.REPLAY.value, "case_id": "semeru-20260923", "auto_replay": False}
        await serving.store.put(Collection.RUNTIME, "state", state)
        await a_moment()
        with candidate.picture_only():
            await candidate.restore_replay_choice()
        assert candidate.mode is RunMode.REPLAY, "it will serve the replay the Desk chose"
        assert candidate.standing_by is True
        assert await writer(candidate) == serving.instance_id
        assert await entries(settings) == []
        assert await serving.store.get(Collection.RUNTIME, "state") == state
    finally:
        for runtime in (serving, candidate):
            runtime.retired = True
            await runtime.aclose()


async def test_the_startup_tick_of_a_standing_by_instance_never_claims(
    settings: Settings, pair: tuple[Runtime, Runtime]
) -> None:
    serving, candidate = pair
    await serving.restore()
    await serving.claim_writer()
    await candidate.restore()
    with candidate.picture_only(), pytest.raises(audit.NotWriter):
        await audit.record(candidate.store, actor=SYSTEM_ACTOR, action=AuditAction.SUPERSEDED)
    assert candidate.standing_by is True
    assert await writer(candidate) == serving.instance_id
    assert await entries(settings) == []


async def test_create_runtime_stands_by_under_cloud_scheduler_only(tmp_path: Path) -> None:
    for local, standing in ((False, True), (True, False)):
        settings = make_settings(
            tmp_path / str(local),
            mode=RunMode.REPLAY,
            replay_case="semeru-20260923",
            data_dir=DATA_DIR,
            local_scheduler=local,
        )
        runtime = await create_runtime(settings)
        try:
            assert runtime.standing_by is standing
            assert audit._gates.get(runtime.store) is not None
        finally:
            await runtime.aclose()
        assert audit._gates.get(runtime.store) is None, "closing removes the gate"


# --- AI failures audited once ------------------------------------------------------------------


def failure(cone: str, **changes: object) -> AiFailure:
    base = AiFailure(
        id=f"AIF-{cone}",
        created_at=AT,
        replay=True,
        stage="duty_officer",
        reason="DUTY OFFICER AI UNAVAILABLE: budget_exhausted",
        model_id="gemini-3.5-flash-lite",
        volcano_id="262000",
        volcano_name="Anak Krakatau",
        flight_id="8a0365:262000",
        proxy_flight="RFA6156",
        hex="8a0365",
        cone_id=cone,
        minutes_to_entry=0,
        inside_now=True,
    )
    return base.model_copy(update=changes)


async def test_a_failure_repeated_every_tick_is_audited_once_and_shown_every_time(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "f.sqlite3", tmp_path / "blobs")
    bus = EventBus()
    queue = bus.subscribe()
    try:
        previous: AiFailure | None = None
        for minute in range(6):  # a new cone id each minute, the same reason
            recorded = await record_failure(store, bus, failure(f"CONE-{minute}"))
            assert recorded is not None
            if previous is not None:
                await close_failure(store, bus, previous.id, reason=NEWER_FAILURE)
            previous = recorded
        assert previous is not None
        await close_failure(store, bus, previous.id, reason="POSITION LOST FOR 10 MIN")
        listed = await list_failures(store, open_only=False, limit=50)
        assert len(listed) == 6, "every failure is stored for the Desk"
        events = [await queue.get(within_s=0.5) for _ in range(12)]
        assert all(e is not None and e.name == SseEvent.AI_FAILURE for e in events)
        logged = await audit.list_entries(store, limit=50)
        assert [(e.action, e.note) for e in reversed(logged)] == [
            (AuditAction.AI_FAILED, "DUTY OFFICER AI UNAVAILABLE: budget_exhausted"),
            (AuditAction.AI_FAILURE_CLOSED, NEWER_FAILURE),
        ], "the first failure and its close; the repeats add nothing to the record"

        other = await record_failure(store, bus, failure("CONE-9", reason="NO DRAFT RETURNED"))
        assert other is not None
        assert len(await audit.list_entries(store, limit=50)) == 3, "a new reason is audited"
    finally:
        await store.aclose()


async def test_the_next_quota_day_audits_the_failure_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = SqliteStore(tmp_path / "f.sqlite3", tmp_path / "blobs")
    bus = EventBus()
    days = iter([date(2026, 10, 18), date(2026, 10, 18), date(2026, 10, 19)])
    monkeypatch.setattr(failures, "quota_day", lambda _at: next(days))
    try:
        for cone in ("A", "B", "C"):
            await record_failure(store, bus, failure(cone))
        logged = await audit.list_entries(store, limit=50)
        assert [e.after["cone_id"] for e in reversed(logged) if e.after] == ["A", "C"]
    finally:
        await store.aclose()


async def test_a_close_of_a_failure_another_instance_recorded_is_audited(tmp_path: Path) -> None:
    path, blobs = tmp_path / "f.sqlite3", tmp_path / "blobs"
    first = SqliteStore(path, blobs)
    recorded = await record_failure(first, EventBus(), failure("A"))
    assert recorded is not None
    await first.aclose()
    later = SqliteStore(path, blobs)
    try:
        await close_failure(later, EventBus(), recorded.id, reason="POSITION LOST FOR 10 MIN")
        actions = [e.action for e in await audit.list_entries(later, limit=10)]
        assert actions == [AuditAction.AI_FAILURE_CLOSED, AuditAction.AI_FAILED]
    finally:
        await later.aclose()


# --- a fork repair asks the serving instance to walk again ------------------------------------


async def test_a_repair_after_the_last_walk_is_walked_at_the_next_checkpoint(
    settings: Settings,
) -> None:
    runtime = make_runtime(settings, FixtureSource())
    other = SqliteStore(settings.sqlite_path, settings.cache_dir / "blobs")
    try:
        first = await audit.record(runtime.store, actor=SYSTEM_ACTOR, action=AuditAction.LOGIN_OK)
        assert isinstance(first, audit.ChainedAuditEntry)
        kept = await audit.record(runtime.store, actor=SYSTEM_ACTOR, action=AuditAction.LOGIN_OK)
        assert kept.seq == 2
        stray = first.model_copy(
            update={
                "id": "-stray",
                "seq": 2,
                "prev_sha256": first.sha256,
                "note": "a second writer",
            }
        )
        await other.append_audit(stray.model_copy(update={"sha256": audit.entry_digest(stray)}))
        third = await audit.record(runtime.store, actor=SYSTEM_ACTOR, action=AuditAction.LOGIN_OK)
        assert third.prev_sha256 == kept.sha256, "the newest by seq (ties by id) is the kept one"
        await runtime.restore()
        head = runtime.audit_head
        assert head is not None
        assert head.problems == ["fork at seq 2"]

        await runtime.checkpoint(force=True)
        assert runtime.audit_head == head, "no repair yet: no walk"

        await other.delete(Collection.AUDIT, "-stray")  # what the repair does, after its copy
        repaired_at = timeutil.SystemClock().now() + timedelta(seconds=1)
        await other.put(
            Collection.RUNTIME, audit.REPAIR_DOC, {"repaired_at": timeutil.to_iso(repaired_at)}
        )
        runtime._last_checkpoint = None
        await runtime.checkpoint(force=True)
        walked = runtime.audit_head
        assert walked is not None
        assert (walked.seq, walked.intact, walked.problems) == (3, True, [])
        persisted = await other.get(Collection.RUNTIME, AUDIT_HEAD_DOC)
        assert persisted is not None
        assert persisted["verified_through_seq"] == 3

        runtime._last_checkpoint = None
        await runtime.checkpoint(force=True)
        assert runtime.audit_head == walked, "an intact head reads no repair note"
    finally:
        await other.aclose()
        await runtime.aclose()


# --- a request on an instance that has handed over ---------------------------------------------


class GatedHarness:
    """A Desk app whose store's audit gate answers ``allow`` (one answer per call, the last
    repeated), as an old instance's does once a new one has claimed the writer."""

    def __init__(self, *allow: bool) -> None:
        self.allow = list(allow)
        self.store: Store | None = None

    async def gate(self) -> bool:
        return self.allow.pop(0) if len(self.allow) > 1 else self.allow[0]

    async def factory(self, settings: Settings) -> Runtime:
        self.store = open_store(settings)
        audit.gate(self.store, self.gate)
        return cast(Runtime, FakeRuntime(settings=settings, store=self.store))


def desk_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        llm="stub",
        store="sqlite",
        sqlite_path=tmp_path / "tephra.sqlite3",
        cache_dir=tmp_path / "cache",
        data_dir=tmp_path / "data",
        desk_pin=PIN,
        session_secret="test-session-secret-0123456789abcdef",
        local_scheduler=False,
    )


async def stored_entries(store: Store | None) -> list[dict[str, object]]:
    assert store is not None
    return await store.list_docs(Collection.AUDIT, limit=10, order_by="seq", descending=False)


def test_a_request_that_writes_on_an_instance_that_handed_over_is_refused_first(
    tmp_path: Path,
) -> None:
    """Simulated rollout: the old instance's late Desk request answered 500 after its writes
    were stored, with no audit entry. Now it is refused before the route runs, so nothing is
    stored without its entry; reads still answer."""
    harness = GatedHarness(False)
    with TestClient(create_app(desk_settings(tmp_path), runtime_factory=harness.factory)) as client:
        response = client.post("/api/desk/login", json={"pin": PIN, "name": DISPATCHER})
        assert response.status_code == 503
        assert response.json()["error"] == "handed_over"
        assert response.headers["retry-after"] == str(HANDED_OVER_RETRY_S)
        assert "set-cookie" not in response.headers
        assert client.get("/health").status_code == 200
        entries_now = client.portal.call(stored_entries, harness.store)
    assert entries_now == []


def test_a_handover_between_the_check_and_the_append_answers_503(tmp_path: Path) -> None:
    harness = GatedHarness(True, False)
    with TestClient(create_app(desk_settings(tmp_path), runtime_factory=harness.factory)) as client:
        response = client.post("/api/desk/login", json={"pin": PIN, "name": DISPATCHER})
        assert response.status_code == 503
        assert response.json()["error"] == "handed_over"


def test_a_writer_instance_takes_requests_as_before(tmp_path: Path) -> None:
    harness = GatedHarness(True)
    with TestClient(create_app(desk_settings(tmp_path), runtime_factory=harness.factory)) as client:
        assert client.post("/api/desk/login", json={"pin": PIN, "name": DISPATCHER}).is_success
        entries_now = client.portal.call(stored_entries, harness.store)
    assert [entry["action"] for entry in entries_now] == [AuditAction.LOGIN_OK.value]


# --- a whole walk's problem below the verified point -------------------------------------------


async def test_a_problem_a_whole_walk_finds_below_the_verified_point_stays(tmp_path: Path) -> None:
    """Review, item 5: an ops manager's whole check finds an edited entry below
    ``verified_through_seq``; a later incremental walk (an "another writer" re-walk) must not
    start past it and report the chain intact."""
    store = SqliteStore(tmp_path / "a.sqlite3", tmp_path / "blobs")
    try:
        written = [
            await audit.record(store, actor=SYSTEM_ACTOR, action=AuditAction.LOGIN_OK, note=str(n))
            for n in range(5)
        ]
        assert (await audit.check_chain(store)).intact
        assert audit.chain(store).verified_through_seq == 5
        edited = written[1].model_dump(mode="json") | {"note": "edited"}
        await store.delete(Collection.AUDIT, written[1].id)
        await store.append_audit(audit.ChainedAuditEntry.model_validate(edited))
        whole = await audit.check_chain(store, whole=True)
        assert not whole.intact
        assert audit.chain(store).verified_through_seq == 0
        again = await audit.check_chain(store)
        assert not again.intact
        assert again.problems == whole.problems
    finally:
        await store.aclose()
