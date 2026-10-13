"""Airline data connections (the Connect page, ``/connect``).

``router`` is mounted under ``/api`` by the app factory. The format, its JSON Schema and an
example are public GETs. Connections are made, listed and revoked with a desk session; the
sample feed is started and stopped the same way. ``POST /api/push/positions`` takes a push with
the connection's key in ``Authorization: Bearer <key>`` and answers record by record.
"""

import json
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Header
from fastapi.responses import Response
from pydantic import Field

from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, RuntimeDep, _actor, _json
from tephra.desk import connections, sample_feed
from tephra.models import (
    MAX_PUSH_POSITIONS,
    POSITIONS_FORMAT,
    ConnectionView,
    PositionBatch,
    PushedPosition,
    PushResult,
    TephraModel,
)
from tephra.util import timeutil

__all__ = ["router"]

router = APIRouter()
MIN_PUSH_GAP_S: Final = 1.0


class NewConnection(TephraModel):
    name: str = Field(min_length=2, max_length=48)


class ConnectionList(TephraModel):
    connections: list[ConnectionView]
    sample_running: bool
    sample_connection_id: str | None


class SampleFeedSwitch(TephraModel):
    on: bool


class FormatInfo(TephraModel):
    format: str
    max_positions: int
    fresh_s: int
    push_url: str
    schema_: dict[str, Any] = Field(alias="schema")


def _schema() -> dict[str, Any]:
    record = PushedPosition.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "TEPHRA aircraft positions push",
        "type": "object",
        "required": ["format", "positions"],
        "properties": {
            "format": {"const": POSITIONS_FORMAT},
            "positions": {"type": "array", "maxItems": MAX_PUSH_POSITIONS, "items": record},
        },
    }


@router.get("/connect/format", response_model=FormatInfo)
async def get_format() -> Response:
    info = FormatInfo(
        format=POSITIONS_FORMAT,
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
    return _download(_schema(), "tephra-positions.schema.json")


@router.get("/connect/sample.json")
async def get_sample_file(runtime: RuntimeDep) -> Response:
    """Real recorded flights at their recorded fixes, timed on TEPHRA's clock now, so the file
    is accepted as it is for the next few minutes."""
    pool = sample_feed.load_pool(runtime.settings.data_dir, runtime.settings.region_preset.bbox)
    flights = sample_feed.pick_flights(pool, runtime.sample_areas(), skip=set(), limit=12)
    return _download(
        sample_feed.sample_batch(flights, timeutil.now()), "tephra-positions.sample.json"
    )


async def _list(runtime: Any) -> ConnectionList:
    found = await connections.list_connections(runtime.store)
    return ConnectionList(
        connections=[connections.view(c) for c in found],
        sample_running=runtime.sample_stop is not None,
        sample_connection_id=runtime.sample_connection_id,
    )


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
    runtime: RuntimeDep,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    """One push from an airline connection. 401 without a live key; 429 when pushes come
    faster than one a second; otherwise 200 with every record's outcome."""
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
    result = await runtime.take_push(connection, body.positions)
    return _json(result)
