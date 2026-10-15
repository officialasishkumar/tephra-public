"""Desk routes for crew and passenger messages and the shift handover.

Every route needs a desk session and every POST a CSRF token. A model that cannot write or
check a message or brief answers 503 ``ai_unavailable``; nothing is substituted.
"""

import re
from collections.abc import Awaitable
from typing import Final

from fastapi import APIRouter, Depends, Response

from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, Limit, RuntimeDep, _actor, _json
from tephra.comms import handover, messages
from tephra.comms.models import (
    CrewPaxMessage,
    DraftMessagesRequest,
    EditMessageRequest,
    HandoverBrief,
    HandoverRequest,
    MessageConflict,
    MessageList,
    MessageStatus,
)
from tephra.models import DecisionRequest, ErrorBody, RejectRequest, RunMode, TephraModel

__all__ = ["router"]

router = APIRouter()

_MESSAGE_ID: Final = re.compile(r"msg_[0-9a-f]{12}")
_HANDOVER_ID: Final = re.compile(r"ho_[0-9a-f]{12}")
_SOURCE_ID: Final = re.compile(r"[A-Za-z0-9._:-]{1,64}")


class AiUnavailableBody(ErrorBody):
    """503 body: ``error`` is ``ai_unavailable`` and ``message`` says why."""

    message: str


def _ai_unavailable(exc: messages.AiUnavailable) -> Response:
    body = AiUnavailableBody(error="ai_unavailable", detail=str(exc), message=str(exc))
    return _json(body, 503)


def _check_message_id(message_id: str) -> None:
    if _MESSAGE_ID.fullmatch(message_id) is None:
        raise ApiError(404, "not_found", "No such message")


def _check_source_id(source_id: str | None) -> None:
    if source_id is not None and _SOURCE_ID.fullmatch(source_id) is None:
        raise ApiError(404, "not_found", "No such advisory or recovery plan")


@router.get("/desk/messages", response_model=MessageList)
async def desk_messages(
    session: DeskSession,
    runtime: RuntimeDep,
    status: MessageStatus = MessageStatus.DRAFT,
    limit: Limit = 50,
) -> Response:
    """Messages in the current mode, newest first."""
    listed = await messages.list_messages(
        runtime.store, status=status, replay=runtime.mode is RunMode.REPLAY, limit=limit
    )
    return _json(MessageList(messages=listed))


@router.post(
    "/desk/messages/draft", response_model=MessageList, dependencies=[Depends(require_csrf)]
)
async def draft_messages(
    body: DraftMessagesRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    """Draft messages from an approved advisory or recovery plan. Targets that already have
    an open or approved message come back unchanged."""
    _check_source_id(body.advisory_id)
    _check_source_id(body.recovery_id)
    try:
        drafted = await messages.draft_messages(
            runtime,
            advisory_id=body.advisory_id,
            recovery_id=body.recovery_id,
            actor=_actor(session),
        )
    except messages.AiUnavailable as exc:
        return _ai_unavailable(exc)
    except messages.SourceNotFound:
        raise ApiError(404, "not_found", "No such advisory or recovery plan") from None
    except messages.SourceNotApproved as exc:
        raise ApiError(409, "source_not_approved", str(exc)) from None
    except messages.SourceUnusable as exc:
        raise ApiError(409, "source_unusable", str(exc)) from None
    return _json(MessageList(messages=drafted))


async def _decided(decision: Awaitable[CrewPaxMessage]) -> Response:
    try:
        return _json(await decision)
    except messages.VersionConflict as exc:
        conflict = MessageConflict(
            detail="The message changed since you loaded it", current=exc.current
        )
        return _json(conflict, 409)
    except messages.MessageNotFound:
        raise ApiError(404, "not_found", "No such message") from None
    except messages.InvalidTransition as exc:
        raise ApiError(409, "invalid_transition", str(exc)) from None
    except messages.EditRejected as exc:
        raise ApiError(
            422, "validation_failed", "Message change rejected", problems=exc.problems
        ) from None


@router.post(
    "/desk/messages/{message_id}/approve",
    response_model=CrewPaxMessage,
    dependencies=[Depends(require_csrf)],
)
async def approve_message(
    message_id: str, body: DecisionRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_message_id(message_id)
    return await _decided(
        messages.approve(
            runtime.store,
            runtime.bus,
            message_id,
            expected_version=body.version,
            actor=_actor(session),
        )
    )


@router.post(
    "/desk/messages/{message_id}/edit",
    response_model=CrewPaxMessage,
    dependencies=[Depends(require_csrf)],
)
async def edit_message(
    message_id: str, body: EditMessageRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_message_id(message_id)
    return await _decided(
        messages.edit_and_approve(
            runtime.store,
            runtime.bus,
            message_id,
            expected_version=body.version,
            bodies=body.bodies,
            actor=_actor(session),
        )
    )


@router.post(
    "/desk/messages/{message_id}/reject",
    response_model=CrewPaxMessage,
    dependencies=[Depends(require_csrf)],
)
async def reject_message(
    message_id: str, body: RejectRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_message_id(message_id)
    return await _decided(
        messages.reject(
            runtime.store,
            runtime.bus,
            message_id,
            expected_version=body.version,
            reason=body.reason,
            actor=_actor(session),
        )
    )


@router.post("/desk/handover", response_model=HandoverBrief, dependencies=[Depends(require_csrf)])
async def desk_handover(
    body: HandoverRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    """Draft the handover brief for the shift since ``since``."""
    try:
        brief = await handover.draft_handover(
            runtime, body.since, body.outgoing or session.name, body.incoming
        )
    except messages.AiUnavailable as exc:
        return _ai_unavailable(exc)
    return _json(brief)


class HandoverList(TephraModel):
    handovers: list[HandoverBrief]


@router.get("/desk/handovers", response_model=HandoverList)
async def list_handovers(session: DeskSession, runtime: RuntimeDep, limit: Limit = 20) -> Response:
    """The shift handover briefs of the current mode, latest first."""
    replay = runtime.mode is RunMode.REPLAY
    briefs = await handover.list_handovers(runtime.store, replay=replay, limit=limit)
    return _json(HandoverList(handovers=briefs))


@router.get("/desk/handover/{handover_id}", response_model=HandoverBrief)
async def get_handover(handover_id: str, session: DeskSession, runtime: RuntimeDep) -> Response:
    if _HANDOVER_ID.fullmatch(handover_id) is None:
        raise ApiError(404, "not_found", "No such handover")
    brief = await handover.get_handover(runtime.store, handover_id)
    if brief is None:
        raise ApiError(404, "not_found", "No such handover")
    return _json(brief)


@router.post(
    "/desk/handover/{handover_id}/ack",
    response_model=HandoverBrief,
    dependencies=[Depends(require_csrf)],
)
async def ack_handover(handover_id: str, session: DeskSession, runtime: RuntimeDep) -> Response:
    """The incoming dispatcher's read-back; open drafts are recorded as handed over open."""
    if _HANDOVER_ID.fullmatch(handover_id) is None:
        raise ApiError(404, "not_found", "No such handover")
    try:
        brief = await handover.acknowledge(runtime, handover_id, actor=_actor(session))
    except handover.HandoverNotFound:
        raise ApiError(404, "not_found", "No such handover") from None
    return _json(brief)
