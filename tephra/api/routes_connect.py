"""Airline data connections (the Desk's Data connections; ``/connect`` redirects to onboarding).

``router`` is mounted under ``/api`` by the app factory. The format, its JSON Schema and an
example are public GETs. Connections are made, listed and revoked with a desk session; the
sample feed is started and stopped the same way. ``POST /api/push/positions`` takes a push with
the connection's key in ``Authorization: Bearer <key>`` and answers record by record.

Under a hosted airline (``/a/<ICAO>/api``) the push key was already checked by the airline
dependency, from memory: in setup a push is checked and counted, never taken in (202); once
running it is taken under the airline's limits, and counted in memory for its Feeds page.
"""

import json
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import Response
from pydantic import Field

from tephra.airline.models import DryRunResult
from tephra.api import ApiError
from tephra.api.auth import require_csrf, wall_clock_now
from tephra.api.server import DeskSession, RuntimeDep, _actor, _json, get_runtime
from tephra.api.tenancy import TenantScope, TenantScopeDep
from tephra.desk import connections
from tephra.desk.crew_reports import CrewEntry
from tephra.models import (
    AIRLINE_FORMAT,
    MAX_PUSH_PLANS,
    MAX_PUSH_POSITIONS,
    MAX_PUSH_REPORTS,
    POSITIONS_FORMAT,
    ConnectionView,
    ConnectLive,
    PositionBatch,
    PushedFlightPlan,
    PushedPosition,
    PushResult,
    TephraModel,
)
from tephra.util import timeutil

__all__ = ["router"]

router = APIRouter()
MIN_PUSH_GAP_S: Final = 1.0
SECTIONS: Final = ("positions", "flight_plans", "pilot_reports")


class NewConnection(TephraModel):
    name: str = Field(min_length=2, max_length=48)


class ConnectionList(TephraModel):
    connections: list[ConnectionView]
    sample_running: bool
    sample_connection_id: str | None


class SampleFeedSwitch(TephraModel):
    on: bool


class Upload(PositionBatch):
    """A file a signed-in dispatcher uploads or pastes in the Desk's Data connections."""

    retime: bool = Field(
        default=True,
        description="Stamp every record with TEPHRA's clock now (a file of the "
        "current picture whose times are old, such as the downloaded sample)",
    )


UPLOAD_CONNECTION = "Uploaded files"


class SetupPush(TephraModel):
    """A push to a hosted airline in setup: checked record by record, not taken in."""

    taken_in: Literal[False] = False
    result: DryRunResult


class FormatInfo(TephraModel):
    format: str
    max_positions: int
    fresh_s: int
    push_url: str
    schema_: dict[str, Any] = Field(alias="schema")


def _schema() -> dict[str, Any]:
    """tephra.airline/1: any of the three sections; tephra.positions/1 is positions only."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "TEPHRA airline push",
        "type": "object",
        "required": ["format"],
        "properties": {
            "format": {"enum": [AIRLINE_FORMAT, POSITIONS_FORMAT]},
            "positions": {
                "type": "array",
                "maxItems": MAX_PUSH_POSITIONS,
                "items": PushedPosition.model_json_schema(),
            },
            "flight_plans": {
                "type": "array",
                "maxItems": MAX_PUSH_PLANS,
                "items": PushedFlightPlan.model_json_schema(),
            },
            "pilot_reports": {
                "type": "array",
                "maxItems": MAX_PUSH_REPORTS,
                "items": CrewEntry.model_json_schema(),
            },
        },
    }


@router.get("/connect/format", response_model=FormatInfo)
async def get_format() -> Response:
    info = FormatInfo(
        format=AIRLINE_FORMAT,
        max_positions=MAX_PUSH_POSITIONS,
        fresh_s=connections.PUSH_FRESH_S,
        push_url="/api/push/positions",
        schema=_schema(),
    )
    return Response(info.model_dump_json(by_alias=True), media_type="application/json")


def _download(body: dict[str, Any], filename: str) -> Response:
    return Response(
        json.dumps(body, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/connect/schema.json")
async def get_schema_file() -> Response:
    return _download(_schema(), "tephra-airline.schema.json")


@router.get("/connect/sample.json")
async def get_sample_file(runtime: RuntimeDep) -> Response:
    """Every section of tephra.airline/1 from real recorded flights, timed on TEPHRA's clock now,
    so the file is accepted as it is for the next few minutes."""
    return _download(runtime.sample_bundle(), "tephra-airline.sample.json")


async def _list(runtime: Any) -> ConnectionList:
    found = await connections.list_connections(runtime.store)
    return ConnectionList(
        connections=[connections.view(c) for c in found],
        sample_running=runtime.sample_stop is not None,
        sample_connection_id=runtime.sample_connection_id,
    )


@router.get("/connect/live", response_model=ConnectLive)
async def get_live(runtime: RuntimeDep) -> Response:
    """Every pushed flight and flow now, so a reader starts whole (the ``push`` event follows)."""
    return _json(runtime.connect_live())


@router.post("/desk/upload", response_model=PushResult, dependencies=[Depends(require_csrf)])
async def upload(
    body: Upload, session: DeskSession, runtime: RuntimeDep, scope: TenantScopeDep
) -> Response:
    """A file uploaded or pasted on the page, taken through the "Uploaded files" connection
    (made the first time) exactly as a push. A hosted airline's upload is never retimed: its
    picture is live, and a file stamped "now" would put old positions on it as current."""
    retime = body.retime
    if scope is not None:
        if "retime" in body.model_fields_set and body.retime:
            raise ApiError(
                422,
                "retime_not_on_hosted",
                "Positions keep their own times here",
                problems=["retime: not offered for an airline's live picture"],
            )
        retime = False
    found = [
        c
        for c in await connections.list_connections(runtime.store)
        if c.name == UPLOAD_CONNECTION and not c.sample and c.revoked_at is None
    ]
    connection = found[0] if found else None
    if connection is None:
        connection, _ = await connections.create_connection(
            runtime.store, UPLOAD_CONNECTION, actor=_actor(session)
        )
    taken = await runtime.take_push(
        connection,
        body.positions,
        plans=body.flight_plans,
        reports=body.pilot_reports,
        retime=retime,
    )
    return _json(taken)


@router.get("/desk/connections", response_model=ConnectionList)
async def get_connections(session: DeskSession, runtime: RuntimeDep) -> Response:
    return _json(await _list(runtime))


@router.post(
    "/desk/connections", response_model=ConnectionView, dependencies=[Depends(require_csrf)]
)
async def post_connection(
    body: NewConnection, session: DeskSession, runtime: RuntimeDep
) -> Response:
    """A new connection; the answer carries its key, the only time it is shown."""
    connection, key = await connections.create_connection(
        runtime.store, body.name, actor=_actor(session)
    )
    return _json(connections.view(connection, key))


@router.post(
    "/desk/connections/{connection_id}/revoke",
    response_model=ConnectionView,
    dependencies=[Depends(require_csrf)],
)
async def revoke(connection_id: str, session: DeskSession, runtime: RuntimeDep) -> Response:
    try:
        connection = await connections.revoke_connection(
            runtime.store, connection_id, actor=_actor(session)
        )
    except connections.ConnectionNotFound:
        raise ApiError(404, "not_found", "No such connection") from None
    if connection.id == runtime.sample_connection_id:
        runtime.stop_sample_feed()
    return _json(connections.view(connection))


@router.post(
    "/desk/sample-feed", response_model=ConnectionList, dependencies=[Depends(require_csrf)]
)
async def switch_sample(
    body: SampleFeedSwitch, session: DeskSession, runtime: RuntimeDep
) -> Response:
    if body.on:
        await runtime.start_sample_feed(actor=_actor(session))
    else:
        runtime.stop_sample_feed()
    return _json(await _list(runtime))


@router.post("/push/positions", response_model=PushResult)
async def push_positions(
    body: PositionBatch,
    request: Request,
    scope: TenantScopeDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """One push from an airline connection. 401 without a live key; 429 when pushes come
    faster than one a second; otherwise 200 with every record's outcome."""
    if scope is not None:
        return await _hosted_push(body, request, scope)
    runtime = get_runtime(request, None)
    scheme, _, key = (authorization or "").partition(" ")
    connection = (
        await connections.find_by_key(runtime.store, key.strip())
        if scheme.lower() == "bearer"
        else None
    )
    if connection is None:
        raise ApiError(401, "unauthenticated", "A live connection key is required")
    last = connection.last_push_at
    if last is not None and 0 <= (timeutil.now() - last).total_seconds() < MIN_PUSH_GAP_S:
        raise ApiError(429, "too_many_pushes", "At most one push a second per connection")
    result = await runtime.take_push(
        connection, body.positions, plans=body.flight_plans, reports=body.pilot_reports
    )
    return _json(result)


async def _hosted_push(body: PositionBatch, request: Request, scope: TenantScope) -> Response:
    """The airline's push, its key checked already (``tenant_scope``, no store read), under
    the airline's limits (one push per key every ``hosted_push_gap_s``, 30 a minute)."""
    connection = scope.connection
    assert connection is not None, "a push scope carries its key's connection"
    space = scope.handle.space
    at = wall_clock_now()
    settings = request.app.state.settings
    wait = space.conn_stats.wait_s(connection, at=at, gap_s=settings.hosted_push_gap_s)
    if wait is not None:
        raise _too_fast(f"At most one push every {settings.hosted_push_gap_s:g} s per key", wait)
    throttle = request.app.state.hosted_push
    if throttle.blocked(scope.icao):
        wait_s = throttle.retry_after_s(scope.icao)
        raise _too_fast("At most 30 pushes a minute per airline", wait_s)
    throttle.record_failure(scope.icao)
    sections = [name for name in SECTIONS if getattr(body, name)]
    if scope.handle.record.state == "setup":
        checked = connections.dry_run(body.model_dump(mode="json"), at)
        space.feed_stats.record_dry_run(checked, wall_at=at, connection_id=connection.id)
        accepted, rejected = len(checked.accepted), len(checked.rejected)
        reply = _json(SetupPush(result=checked), status_code=202)
    else:
        result = await get_runtime(request, scope).take_push(
            connection, body.positions, plans=body.flight_plans, reports=body.pilot_reports
        )
        space.feed_stats.record_push(result, wall_at=at)
        accepted, rejected = result.accepted, len(result.rejected)
        reply = _json(result)
    space.conn_stats.note(
        connection.id, accepted=accepted, rejected=rejected, sections=sections, at=at
    )
    return reply


def _too_fast(detail: str, wait_s: float) -> ApiError:
    retry = max(1, int(wait_s + 0.999))
    return ApiError(429, "too_many_pushes", detail, headers={"Retry-After": str(retry)})
