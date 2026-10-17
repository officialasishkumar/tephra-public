"""SHADOW is stamped on the record (D12, S25): every advisory, message, handover brief and
document a hosted airline drafts in SHADOW carries ``shadow`` and a code-written ``SHADOW - NOT
FOR USE`` line outside any body a dispatcher edits. The line survives edit-then-approve and a
switch to LIVE; the demo's text and JSON stay as they were."""

from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest
from test_hosted_runtime import RFB_HEX, hosted_runtime, tick_and_drain
from test_pipeline import AT, FixtureSource, tick_and_work
from test_pipeline import make_runtime as make_demo_runtime
from test_pipeline import make_settings as make_demo_settings

from tephra.agents.dispatch_drafter import header_title
from tephra.comms import messages
from tephra.comms.handover import draft_handover, summary_of
from tephra.config import DEMO_AIRLINE, SHADOW_LINE
from tephra.desk import approvals
from tephra.models import Advisory, AdvisoryStatus, OutboundMessage
from tephra.pipeline import Runtime
from tephra.regdocs.common import stamped_header
from tephra.regdocs.models import VAR_HEADER, DocSummary, SignRole
from tephra.regdocs.registry import sign_doc
from tephra.regdocs.sra import draft_sra
from tephra.regdocs.var import draft_var
from tephra.store.base import Collection
from tephra.store.metered import StoreMeter
from tephra.util.timeutil import FixedClock, use_clock

ACTOR = "desk:Ana Ops#MB-1a2b3c4d5e"


async def _drafts(runtime: Runtime) -> list[Advisory]:
    with runtime.bound():
        return await approvals.list_advisories(runtime.store, status=AdvisoryStatus.DRAFT, limit=50)


async def _outbound(runtime: Runtime) -> list[OutboundMessage]:
    docs = await runtime.store.list_docs(Collection.OUTBOUND, limit=50)
    return [OutboundMessage.model_validate(doc) for doc in docs]


@pytest.fixture
async def shadow_rfb(tmp_path: Path) -> AsyncIterator[Runtime]:
    runtime = await hosted_runtime(tmp_path, StoreMeter(blob_puts_cap=4_000))
    runtime.wall_clock = FixedClock(AT)
    yield runtime
    await runtime.aclose()
    await runtime.store.aclose()


async def test_shadow_advisories_survive_edit_approve_and_the_switch_to_live(
    shadow_rfb: Runtime,
) -> None:
    runtime = shadow_rfb
    await tick_and_drain(runtime)
    drafts = await _drafts(runtime)
    assert drafts, "the stub drafts for RFB417"
    draft = next(d for d in drafts if d.hex == RFB_HEX)
    assert draft.shadow is True
    assert draft.header.splitlines()[0] == SHADOW_LINE
    assert draft.header.splitlines()[1] == header_title(runtime.airline)
    assert draft.model_dump(mode="json")["shadow"] is True

    await runtime.reconfigure(runtime.settings.model_copy(update={"hosted_stage": "live"}))
    with runtime.bound():
        decided = await approvals.edit_and_approve(
            runtime.store,
            runtime.bus,
            draft.id,
            expected_version=draft.version,
            body=draft.final_body + " CREW TO CONFIRM BEFORE DEPARTURE.",
            actor=ACTOR,
        )
        outbound = await _outbound(runtime)
    assert decided.status is AdvisoryStatus.EDITED
    assert decided.shadow is True, "a SHADOW draft keeps its stamp after the flip to LIVE"
    assert len(outbound) == 1
    assert outbound[0].shadow is True
    assert outbound[0].text.splitlines()[0] == SHADOW_LINE
    assert "CREW TO CONFIRM" in outbound[0].text


async def test_shadow_messages_keep_their_line_through_edit_and_approve(
    shadow_rfb: Runtime,
) -> None:
    runtime = shadow_rfb
    await tick_and_drain(runtime)
    draft = next(d for d in await _drafts(runtime) if d.hex == RFB_HEX)
    with runtime.bound():
        approved = await approvals.approve(
            runtime.store, runtime.bus, draft.id, expected_version=draft.version, actor=ACTOR
        )
    await runtime.reconfigure(runtime.settings.model_copy(update={"hosted_stage": "live"}))
    with runtime.bound():
        [briefing] = await messages.draft_messages(runtime, advisory_id=approved.id, actor=ACTOR)
        assert briefing.shadow is True, "a briefing from a SHADOW advisory is not for use"
        language = briefing.texts[0].language
        decided = await messages.edit_and_approve(
            runtime.store,
            runtime.bus,
            briefing.id,
            expected_version=briefing.version,
            bodies={language: briefing.texts[0].body + " Edited by the dispatcher."},
            actor=ACTOR,
            airline=runtime.airline,
        )
        outbound = [o for o in await _outbound(runtime) if o.advisory_id == decided.id]
    assert len(outbound) == 1
    assert outbound[0].shadow is True
    assert outbound[0].text.split("\n\n")[0] == SHADOW_LINE
    assert "Edited by the dispatcher." in outbound[0].text


async def test_shadow_handover_and_documents_are_stamped_outside_editable_fields(
    shadow_rfb: Runtime,
) -> None:
    runtime = shadow_rfb
    await tick_and_drain(runtime)
    flight_id = next(fid for fid, f in runtime.exposed.items() if f.hex == RFB_HEX)
    with runtime.bound():
        brief = await draft_handover(runtime, AT - timedelta(hours=8), "Ana Ops", "Dee Ops")
        var = await draft_var(runtime, flight_id)
        sra = await draft_sra(runtime, runtime.settings.region)
        signed = await sign_doc(
            runtime.store,
            runtime.bus,
            var.id,
            role=SignRole.DISPATCHER,
            name="Ana Ops",
            actor=ACTOR,
        )
    assert brief.shadow is True
    assert summary_of(brief).shadow is True
    for doc in (var, sra, signed):
        assert doc.shadow is True
        assert doc.header.startswith(f"{SHADOW_LINE} - ")
        assert DocSummary.of(doc).shadow is True
    assert signed.header == var.header == stamped_header(VAR_HEADER, shadow=True)


async def _audit(runtime: Runtime) -> list[dict[str, object]]:
    with runtime.bound():
        return await runtime.store.list_docs(Collection.AUDIT, limit=200)


async def test_the_record_tags_every_shadow_draft_and_decision(shadow_rfb: Runtime) -> None:
    """Settings > Record shows the SHADOW tag from ``after.shadow`` (§5.8): every entry about a
    draft made in SHADOW carries it, the decision on it too."""
    runtime = shadow_rfb
    await tick_and_drain(runtime)
    draft = next(d for d in await _drafts(runtime) if d.hex == RFB_HEX)
    flight_id = next(fid for fid, f in runtime.exposed.items() if f.hex == RFB_HEX)
    with runtime.bound():
        approved = await approvals.approve(
            runtime.store, runtime.bus, draft.id, expected_version=draft.version, actor=ACTOR
        )
        await messages.draft_messages(runtime, advisory_id=approved.id, actor=ACTOR)
        await draft_var(runtime, flight_id)
        await draft_handover(runtime, AT - timedelta(hours=8), "Ana Ops", "Dee Ops")
    entries = await _audit(runtime)
    tagged = {str(e["action"]) for e in entries if (e.get("after") or {}).get("shadow") is True}
    assert {"DRAFT_CREATED", "APPROVED", "MESSAGE_DRAFTED", "DOC_DRAFTED"} <= tagged, tagged


async def test_the_demo_is_never_stamped_and_its_json_has_no_shadow_key(
    tmp_path: Path,
) -> None:
    with use_clock(FixedClock(AT)):
        demo = make_demo_runtime(make_demo_settings(tmp_path), FixtureSource())
        try:
            await tick_and_work(demo, reason="manual")
            drafts = await approvals.list_advisories(
                demo.store, status=AdvisoryStatus.DRAFT, limit=50
            )
            draft = drafts[0]
            await approvals.approve(
                demo.store, demo.bus, draft.id, expected_version=draft.version, actor="desk:Ana"
            )
            flight_id = next(iter(demo.exposed))
            var = await draft_var(demo, flight_id)
            brief = await draft_handover(demo, AT - timedelta(hours=8), "Ana", "Dee")
            outbound = await _outbound(demo)
            entries = await demo.store.list_docs(Collection.AUDIT, limit=200)
        finally:
            await demo.aclose()

    assert entries
    assert not any("shadow" in (e.get("after") or {}) for e in entries)

    assert draft.shadow is False
    assert "shadow" not in draft.model_dump(mode="json")
    assert draft.header.splitlines()[0] == header_title(DEMO_AIRLINE)
    assert SHADOW_LINE not in draft.final_text
    assert "shadow" not in outbound[0].model_dump(mode="json")
    assert SHADOW_LINE not in outbound[0].text
    assert var.header == VAR_HEADER
    assert "shadow" not in var.model_dump(mode="json")
    assert "shadow" not in brief.model_dump(mode="json")
    assert "shadow" not in DocSummary.of(var).model_dump(mode="json")


def test_stamped_header_leaves_a_live_header_alone() -> None:
    assert stamped_header(VAR_HEADER, shadow=False) == VAR_HEADER
    assert stamped_header(VAR_HEADER, shadow=True) == f"{SHADOW_LINE} - {VAR_HEADER}"
