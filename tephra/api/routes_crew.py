"""Crew (pilot) reports of ash: entered, listed and withdrawn on the Desk.

``router`` is mounted under ``/api`` by the app factory. Every route needs a desk session and
every POST the CSRF guard. A report is refused (422 ``validation_failed`` with every problem)
rather than completed with a guess. The areas drawn are flags only: nothing here plans,
drafts an advisory or calls a model. The message route starts the message to the weather
office and the VAAC as a document a human signs; nothing is sent.
"""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, RuntimeDep, _actor, _json
from tephra.desk.crew_reports import (
    AlreadyWithdrawn,
    CrewEntry,
    CrewReportNotFound,
    CrewReportRefused,
    FixLookup,
    WithdrawRequest,
)
from tephra.models import CrewPicture, CrewReportView, UtcDatetime
from tephra.regdocs.crew_message import NotAnAshReport, draft_crew_message
from tephra.regdocs.models import CrewMessageDraft

__all__ = ["router"]

_REPORT_ID = re.compile(r"CR-[0-9a-f]{12}")
router = APIRouter()


def _check_report_id(report_id: str) -> None:
    if _REPORT_ID.fullmatch(report_id) is None:
        raise ApiError(404, "not_found", "No such crew report")


def _refused(exc: CrewReportRefused) -> ApiError:
    return ApiError(422, "validation_failed", "Crew report refused", problems=exc.problems)


@router.get("/desk/crew-reports", response_model=CrewPicture)
async def get_crew_reports(session: DeskSession, runtime: RuntimeDep) -> Response:
    """The current mode's picture (also ``WallSnapshot.crew`` and the ``crew`` event)."""
    return _json(runtime.crew)


@router.get("/desk/crew-reports/fix", response_model=FixLookup)
async def get_crew_fix(
    session: DeskSession,
    runtime: RuntimeDep,
    observed_at: UtcDatetime,
    hex: Annotated[str | None, Query(pattern=r"^[0-9a-f]{6}$")] = None,
    callsign: Annotated[str | None, Query(min_length=4, max_length=7)] = None,
) -> Response:
    """The ADS-B fix a report observed at ``observed_at`` would be placed at, or why none."""
    if (hex is None) == (callsign is None):
        raise ApiError(
            422,
            "validation_failed",
            "Name the flight",
            problems=["give exactly one of hex (a tracked flight) and callsign"],
        )
    try:
        return _json(runtime.crew_fix(hex, callsign, observed_at))
    except CrewReportRefused as exc:
        raise _refused(exc) from None


@router.post(
    "/desk/crew-reports", response_model=CrewReportView, dependencies=[Depends(require_csrf)]
)
async def post_crew_report(body: CrewEntry, session: DeskSession, runtime: RuntimeDep) -> Response:
    try:
        view = await runtime.enter_crew_report(body, actor=_actor(session))
    except CrewReportRefused as exc:
        raise _refused(exc) from None
    return _json(view)


@router.post(
    "/desk/crew-reports/{report_id}/withdraw",
    response_model=CrewReportView,
    dependencies=[Depends(require_csrf)],
)
async def withdraw_crew_report(
    report_id: str, body: WithdrawRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    """For an entry error (wrong flight, position or time); the report and its audit stay."""
    _check_report_id(report_id)
    try:
        view = await runtime.withdraw_crew_report(
            report_id, reason=body.reason, actor=_actor(session)
        )
    except CrewReportNotFound:
        raise ApiError(404, "not_found", "No such crew report") from None
    except AlreadyWithdrawn:
        raise ApiError(409, "invalid_transition", "The crew report is already withdrawn") from None
    except CrewReportRefused as exc:
        raise _refused(exc) from None
    return _json(view)


@router.post(
    "/desk/crew-reports/{report_id}/message",
    response_model=CrewMessageDraft,
    dependencies=[Depends(require_csrf)],
)
async def draft_crew_report_message(
    report_id: str, session: DeskSession, runtime: RuntimeDep
) -> Response:
    """Start the message to the weather office and the VAAC from the report (a draft)."""
    _check_report_id(report_id)
    report = runtime.crew_reports.get(report_id)
    if report is None:
        raise ApiError(404, "not_found", "No such crew report")
    view = runtime.crew_view(report_id)
    if view is None:
        raise ApiError(409, "invalid_transition", "The crew report is not in the current picture")
    volcano = runtime.catalogue.get(report.volcano_id) if report.volcano_id else None
    try:
        doc = await draft_crew_message(
            runtime,
            view,
            vaac=volcano.vaac if volcano is not None else None,
            actor=_actor(session),
        )
    except NotAnAshReport:
        raise ApiError(
            409,
            "invalid_transition",
            "Only a crew report of ash that is not withdrawn starts a message",
        ) from None
    return _json(doc)
