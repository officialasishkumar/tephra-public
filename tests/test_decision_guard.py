"""The server-side decision guard: a HYPOTHESIS draft is approved only as MONITOR or HOLD,
an edit cannot add a divert under HYPOTHESIS, and a draft written for an ash area that has
since moved is refused. A refusal audits nothing and queues nothing."""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from test_api import make_advisory

from tephra.agents.validators import hypothesis_body_problems, normalise_number, number_tokens
from tephra.desk import audit
from tephra.desk.approvals import (
    EditRejected,
    RuleBlocked,
    approve,
    edit_and_approve,
    submit_draft,
)
from tephra.models import ActionKind, Advisory, AdvisoryStatus, AuditAction, PlumeMode
from tephra.store.base import Collection
from tephra.store.sqlite_store import SqliteStore
from tephra.util.events import EventBus
from tephra.util.timeutil import FixedClock, use_clock

AT = datetime(2026, 10, 9, 19, 40, tzinfo=UTC)
DESK = "desk:duty"
HYPOTHESIS_REFUSAL = "HYPOTHESIS ALLOWS ONLY MONITOR OR HOLD; REJECT THIS DRAFT"
CHANGED_REFUSAL = "THE ASH AREA CHANGED SINCE THIS DRAFT WAS WRITTEN; A NEW PLAN IS DUE"


@pytest.fixture(autouse=True)
def clock() -> Iterator[None]:
    with use_clock(FixedClock(AT)):
        yield


@pytest.fixture
async def store(tmp_path: Path) -> AsyncIterator[SqliteStore]:
    opened = SqliteStore(tmp_path / "tephra.sqlite3", tmp_path / "blobs")
    yield opened
    await opened.aclose()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


def draft(**changes: object) -> Advisory:
    return make_advisory().model_copy(update=changes)


async def submitted(store: SqliteStore, bus: EventBus, advisory: Advisory) -> Advisory:
    created = await submit_draft(store, bus, advisory)
    assert created is not None
    return created


async def untouched(store: SqliteStore, advisory_id: str) -> None:
    """A refusal leaves the draft, the audit trail and the outbound queue as they were."""
    doc = await store.get(Collection.ADVISORIES, advisory_id)
    assert doc is not None
    current = Advisory.model_validate(doc)
    assert (current.status, current.version) == (AdvisoryStatus.DRAFT, 1)
    entries = await audit.list_entries(store, advisory_id=advisory_id)
    assert [entry.action for entry in entries] == [AuditAction.DRAFT_CREATED]
    queued = await store.list_docs(Collection.OUTBOUND, limit=10)
    assert [doc for doc in queued if doc["advisory_id"] == advisory_id] == []


async def test_a_hypothesis_draft_can_only_be_approved_as_monitor_or_hold(
    store: SqliteStore, bus: EventBus
) -> None:
    divert = await submitted(
        store,
        bus,
        draft(
            plume_mode=PlumeMode.HYPOTHESIS,
            action=ActionKind.DIVERT,
            alternate_icao="WADD",
            body="DIVERT TO WADD. ASH SFC/FL150 AHEAD, ENTRY 14 MIN. REPORT VAR.",
        ),
    )
    with pytest.raises(RuleBlocked) as refused:
        await approve(store, bus, divert.id, expected_version=1, actor=DESK)
    assert refused.value.code == "rule_blocked"
    assert refused.value.problems == [HYPOTHESIS_REFUSAL]
    await untouched(store, divert.id)

    with pytest.raises(RuleBlocked) as refused_edit:
        await edit_and_approve(
            store,
            bus,
            divert.id,
            expected_version=1,
            body="MONITOR ASH AHEAD. REPORT VAR.",
            actor=DESK,
        )
    assert refused_edit.value.code == "rule_blocked"
    await untouched(store, divert.id)

    hold = await submitted(
        store,
        bus,
        draft(
            id="adv_hold00000000",
            flight_id="8a0777:263300",
            hex="8a0777",
            dedupe_key="DD-hold00000000",
            plume_mode=PlumeMode.HYPOTHESIS,
            action=ActionKind.HOLD,
        ),
    )
    approved = await approve(store, bus, hold.id, expected_version=1, actor=DESK)
    assert approved.status is AdvisoryStatus.APPROVED


async def test_an_edit_cannot_add_a_divert_to_a_hypothesis_draft(
    store: SqliteStore, bus: EventBus
) -> None:
    hold = await submitted(
        store, bus, draft(plume_mode=PlumeMode.HYPOTHESIS, action=ActionKind.HOLD)
    )
    with pytest.raises(EditRejected) as rejected:
        await edit_and_approve(
            store,
            bus,
            hold.id,
            expected_version=1,
            body="HOLD PRESENT POSITION FL350 THEN DIVERT TO WADD. REPORT VAR.",
            actor=DESK,
        )
    assert rejected.value.problems == [
        "BODY MUST NOT ADVISE DIVERT WITHOUT A VALID OFFICIAL PRODUCT (HYPOTHESIS MODE)"
    ]
    await untouched(store, hold.id)

    edited = await edit_and_approve(
        store,
        bus,
        hold.id,
        expected_version=1,
        body="HOLD PRESENT POSITION FL350. ASH AHEAD. REPORT VAR.",
        actor=DESK,
    )
    assert edited.status is AdvisoryStatus.EDITED

    # The same words pass under OFFICIAL: the rule belongs to HYPOTHESIS alone.
    official = await submitted(
        store,
        bus,
        draft(
            id="adv_offic0000000",
            flight_id="8a0888:263300",
            hex="8a0888",
            dedupe_key="DD-offic0000000",
        ),
    )
    accepted = await edit_and_approve(
        store,
        bus,
        official.id,
        expected_version=1,
        body="HOLD PRESENT POSITION FL350 THEN DIVERT TO WADD. REPORT VAR.",
        actor=DESK,
    )
    assert accepted.status is AdvisoryStatus.EDITED


async def test_a_draft_for_an_older_cone_is_not_approved(store: SqliteStore, bus: EventBus) -> None:
    created = await submitted(store, bus, draft(cone_id="CONE-0123456789ab", plan_key=None))
    with pytest.raises(RuleBlocked) as refused:
        await approve(
            store,
            bus,
            created.id,
            expected_version=1,
            actor=DESK,
            current_cone_id="CONE-other",
        )
    assert refused.value.code == "cone_changed"
    assert refused.value.problems == [CHANGED_REFUSAL]
    await untouched(store, created.id)

    with pytest.raises(RuleBlocked) as refused_edit:
        await edit_and_approve(
            store,
            bus,
            created.id,
            expected_version=1,
            body="HOLD PRESENT POSITION FL350. REPORT VAR.",
            actor=DESK,
            current_cone_id="CONE-other",
        )
    assert refused_edit.value.code == "cone_changed"
    await untouched(store, created.id)

    # None means the caller cannot say; the same id means nothing moved.
    same = await submitted(
        store,
        bus,
        draft(
            id="adv_same00000000",
            flight_id="8a0999:263300",
            hex="8a0999",
            dedupe_key="DD-same00000000",
            cone_id="CONE-0123456789ab",
        ),
    )
    decided = await approve(
        store,
        bus,
        same.id,
        expected_version=1,
        actor=DESK,
        current_cone_id="CONE-0123456789ab",
    )
    assert decided.status is AdvisoryStatus.APPROVED
    unknown = await submitted(
        store,
        bus,
        draft(
            id="adv_none00000000",
            flight_id="8a0aaa:263300",
            hex="8a0aaa",
            dedupe_key="DD-none00000000",
        ),
    )
    decided = await approve(store, bus, unknown.id, expected_version=1, actor=DESK)
    assert decided.status is AdvisoryStatus.APPROVED


async def test_plan_key_outranks_cone_id_when_both_are_known(
    store: SqliteStore, bus: EventBus
) -> None:
    created = await submitted(store, bus, draft(cone_id="CONE-old", plan_key="0123456789abcdef"))
    decided = await approve(
        store,
        bus,
        created.id,
        expected_version=1,
        actor=DESK,
        current_cone_id="CONE-new",
        current_plan_key="0123456789abcdef",
    )
    assert decided.status is AdvisoryStatus.APPROVED

    other = await submitted(
        store,
        bus,
        draft(
            id="adv_plan00000000",
            flight_id="8a0bbb:263300",
            hex="8a0bbb",
            dedupe_key="DD-plan00000000",
            cone_id="CONE-same",
            plan_key="0123456789abcdef",
        ),
    )
    with pytest.raises(RuleBlocked) as refused:
        await approve(
            store,
            bus,
            other.id,
            expected_version=1,
            actor=DESK,
            current_cone_id="CONE-same",
            current_plan_key="fedcba9876543210",
        )
    assert refused.value.code == "cone_changed"
    await untouched(store, other.id)


def test_the_number_rule_is_exported_under_public_names() -> None:
    assert number_tokens("ASH FL150 TO FL350, 1,200 KG, 2.5 H") == {"150", "350", "1200", "2.5"}
    assert normalise_number(350.0) == "350"
    assert normalise_number(2.5) == "2.5"
    assert hypothesis_body_problems("MONITOR ASH AHEAD. HOLD FL350.") == []
    assert hypothesis_body_problems("CLIMB FL370 THEN DIVERSION TO WADD") == [
        "BODY MUST NOT ADVISE CLIMB WITHOUT A VALID OFFICIAL PRODUCT (HYPOTHESIS MODE)",
        "BODY MUST NOT ADVISE DIVERSION WITHOUT A VALID OFFICIAL PRODUCT (HYPOTHESIS MODE)",
    ]
