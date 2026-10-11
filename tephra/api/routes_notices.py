"""Pasted volcano notices: read by Gemini, verified by code, listed for the Wall and Desk.

``POST /desk/notices`` is a dispatcher action: it spends at most two lite model calls, so a
notice already read (same text, however spaced) is answered from the store instead. The
reading is stored and audited whether or not it verified; only a verified one carries a
``Vona``, which joins the live picture (``Runtime.add_verified_notice``). A model failure is
stored as ``ai_unavailable`` and answered with HTTP 503 ``ai_unavailable``; nothing is
substituted.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

from tephra.agents.notice_reader import (
    JMA_SOURCE_PREFIX,
    MAX_NOTICE_CHARS,
    NoticeReading,
    jma_reading,
    normalise_notice,
    notice_id,
    read_notice,
)
from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, RuntimeDep, _actor, _json
from tephra.desk import audit
from tephra.models import AuditAction, RunMode, SseEvent, TephraModel
from tephra.store.base import Collection

__all__ = ["NoticeList", "NoticeRequest", "router"]

MIN_NOTICE_CHARS = 20
router = APIRouter()
Limit = Annotated[int, Query(ge=1, le=100)]


class NoticeRequest(TephraModel):
    text: str = Field(max_length=MAX_NOTICE_CHARS, description="The notice as pasted")


class NoticeList(TephraModel):
    notices: list[NoticeReading]


@router.post("/desk/notices", response_model=NoticeReading, dependencies=[Depends(require_csrf)])
async def post_notice(body: NoticeRequest, session: DeskSession, runtime: RuntimeDep) -> Response:
    text = normalise_notice(body.text)
    if len(text) < MIN_NOTICE_CHARS:
        raise ApiError(
            422,
            "validation_failed",
            "Notice is too short to read",
            problems=[f"text: at least {MIN_NOTICE_CHARS} characters"],
        )
    stored = await runtime.store.get(Collection.NOTICES, notice_id(text))
    if stored is not None and stored.get("status") != "ai_unavailable":
        known = NoticeReading.model_validate(stored)
        if known.vona is not None:  # idempotent: after a restart the picture may have lost it
            await runtime.add_verified_notice(known.vona)
        return _json(known)

    reading = await read_notice(
        text, runtime.llm, runtime.catalogue, replay=runtime.mode is RunMode.REPLAY
    )
    await runtime.store.put(Collection.NOTICES, reading.id, reading.model_dump(mode="json"))
    await audit.record(
        runtime.store,
        actor=_actor(session),
        action=AuditAction.NOTICE_READ,
        after={
            "notice_id": reading.id,
            "status": reading.status,
            "volcano": reading.vona.volcano_name if reading.vona else None,
            "fields": [field.name for field in reading.fields],
        },
        input_hashes=[reading.sha256],
        model_id=reading.model_id,
        prompt_hash=reading.prompt_hash,
        note=reading.reason,
    )
    runtime.bus.publish(SseEvent.NOTICE, reading)
    if reading.vona is not None:  # verified: it joins the live picture like a VONA
        await runtime.add_verified_notice(reading.vona)
    if reading.status == "ai_unavailable":
        raise ApiError(503, "ai_unavailable", reading.reason or "AI UNAVAILABLE")
    return _json(reading)


@router.get("/notices", response_model=NoticeList)
async def get_notices(runtime: RuntimeDep, limit: Limit = 50) -> Response:
    """Notices read in the current mode, newest first: pasted ones and the JMA volcano reports
    (``JMA-`` records of the live picture, read by code, so verified and in Japanese)."""
    docs = await runtime.store.query(
        Collection.NOTICES, [], order_by="created_at", descending=True, limit=200
    )
    replay = runtime.mode is RunMode.REPLAY
    notices = [NoticeReading.model_validate(doc) for doc in docs]
    notices = [n for n in notices if n.replay == replay]
    notices += [
        jma_reading(vona, replay=replay)
        for vona in runtime.live.vonas.values()
        if vona.provenance.source_id.startswith(JMA_SOURCE_PREFIX)
    ]
    notices.sort(key=lambda n: n.created_at, reverse=True)
    return _json(NoticeList(notices=notices[:limit]))
