"""The FastAPI app: the read API, desk decisions, SSE and the tick task (the pages are
``tephra.api.routes_pages``).

Routes and JSON shapes are the contract in MODULES.md section 8. Every body is a model from
``tephra.models`` dumped in JSON mode; every error is an ``ErrorBody`` and never carries a
stack trace or echoes request input. Nothing here calls an external system: approvals only
reach the ``outbound`` collection through ``tephra.desk.approvals``.
"""

import asyncio
import contextvars
import json
import logging
import os
import re
import secrets
import sys
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Final, Self

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tephra import __version__
from tephra.airline.sessions import THROTTLES as AIRLINE_THROTTLES
from tephra.api import ApiError
from tephra.api.auth import (
    LoginThrottle,
    actor_of,
    clear_session_cookie,
    client_key,
    desk_enabled,
    is_https,
    new_session_id,
    pin_matches,
    require_csrf,
    require_desk,
    require_desk_enabled,
    require_task_token,
    set_session_cookie,
    sign_session,
    wall_clock_now,
)
from tephra.api.routes_pages import WEB_DIR
from tephra.api.routes_pages import router as pages
from tephra.api.sse import (
    TENANT_STREAM_CHECK_S,
    TENANT_STREAM_LIFETIME_S,
    TENANT_STREAMS_PER_MEMBER,
    EventStreamResponse,
    StreamSlots,
    event_stream,
    parse_last_event_id,
)
from tephra.api.tenancy import (
    RUN,
    TenantPathMiddleware,
    TenantScope,
    TenantScopeDep,
    build_route_index,
    scoped_routes_missing,
    tenant_scope,
)
from tephra.config import (
    MAX_BODY_BYTES,
    MAX_NOTICE_BODY_BYTES,
    MAX_ONBOARD_BODY_BYTES,
    MAX_PUSH_BODY_BYTES,
    Settings,
    get_settings,
)
from tephra.desk import approvals, audit, failures
from tephra.feeds.routes import route_features
from tephra.models import (
    ActionKind,
    Advisory,
    AdvisoryList,
    AdvisoryStatus,
    AiFailure,
    AiFailureList,
    AuditAction,
    AuditList,
    ChainHead,
    DecisionRequest,
    EditRequest,
    ErrorBody,
    FeedHealth,
    HandledRequest,
    LoginRequest,
    OutboundList,
    OutboundMessage,
    PolicyResponse,
    RejectRequest,
    ReplayCase,
    RunMode,
    SessionInfo,
    SseEvent,
    SystemState,
    TephraModel,
    TickReport,
    TraceEvent,
    TraceStage,
    UtcDatetime,
    WallResponse,
)
from tephra.pipeline import OPEN_DRAFT_LIMIT, Runtime, create_runtime
from tephra.replay.cases import list_cases, load_case, replay_banner
from tephra.scheduler import run_local_scheduler, run_writer_watchdog
from tephra.store.base import BLOB_KEY_PATTERN, Collection
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes
from tephra.util.scope import current_tenant

if TYPE_CHECKING:
    from tephra.hosted.access import AccessCache
    from tephra.hosted.registry import TenantRegistry
    from tephra.store.base import Store
    from tephra.store.metered import StoreMeter

__all__ = ["CONTENT_SECURITY_POLICY", "WEB_DIR", "configure_logging", "create_app"]

logger = logging.getLogger(__name__)

CONTENT_SECURITY_POLICY: Final = "; ".join(
    [
        "default-src 'self'",
        # Scripts only from the two pinned packages (docs/UI-DESIGN.md, THIRD_PARTY.md).
        "script-src 'self' https://unpkg.com/maplibre-gl@4.7.1/"
        " https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/",
        "style-src 'self' https://unpkg.com/maplibre-gl@4.7.1/"
        " https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/",
        # Map tiles: OpenFreeMap basemap, NASA GIBS satellite context, Mapterhorn terrain; the map
        # card's freely licensed photos: Wikidata finds them, Commons checks the licence and serves.
        "img-src 'self' data: blob: https://tiles.openfreemap.org"
        " https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com"
        " https://upload.wikimedia.org https://thumb.wikimedia.org",
        "connect-src 'self' https://tiles.openfreemap.org"
        " https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com"
        " https://query.wikidata.org https://commons.wikimedia.org",
        # Ask TEPHRA's spoken answers are WAV files played from a blob: URL.
        "media-src 'self' blob:",
        "worker-src 'self' blob:",
        "child-src blob:",
        "font-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'none'",
        "form-action 'self'",
    ]
)
DESK_PATH: Final = "/desk"
DESK_PERMISSIONS_POLICY: Final = "camera=(), microphone=(self), geolocation=()"
"""Only the Desk page may ask for the microphone (push-to-talk in Ask TEPHRA)."""
VOICE_PATH: Final = "/api/desk/ask/voice"
NOTICE_PATH: Final = "/api/desk/notices"
ONBOARD_PATHS: Final = frozenset(
    {"/api/airline/accounts", "/api/airline/answers", "/api/airline/draft", "/api/airline/submit"}
)
PUSH_BODY_PATHS: Final = frozenset(
    {
        "/api/push/positions",
        "/api/desk/upload",
        "/api/airline/feeds/dry-run",
        "/api/tenant/feeds/dry-run",
    }
)
HOSTED_KEY_ENV: Final = ("GOOGLE_API_KEY", "GEMINI_API_KEY")
"""Removed from the process environment when ``hosted`` is on: every model client gets its key
passed in, so a client that would read the environment finds nothing (fails closed)."""
SECURITY_HEADERS: Final = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
STREAMS_RETRY_AFTER_S: Final = 5
"""The Wall and the Desk reopen a refused event stream after 5 s on their own."""
VISITOR_MINTS_PER_WINDOW: Final = 10
VISITOR_MINT_WINDOW_S: Final = 600.0
"""Visitor sessions one client may open in ten minutes (429 ``too_many_visitors`` past it)."""
AUDIT_VERIFY_NOTE: Final = (
    "walked from the first entry at startup; later entries are linked as written"
)
CLOUD_TRACE_HEADER: Final = "x-cloud-trace-context"
TRACEPARENT_HEADER: Final = "traceparent"
_CLOUD_TRACE = re.compile(r"^([0-9a-fA-F]{32})(?:/(\d{1,20}))?(?:;o=([01]))?$")
_TRACEPARENT = re.compile(r"^[0-9a-fA-F]{2}-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-([0-9a-fA-F]{2})$")
SCHEDULER_STOP_TIMEOUT_S: Final = 10.0
GZIP_MIN_BYTES: Final = 1024
"""Responses smaller than this go out uncompressed; gzip would not pay for itself."""

REASON_ACTIONS: Final = frozenset({ActionKind.CONTINUE, ActionKind.MONITOR})
"""Advice that keeps a flight on a route a crew report flags: approving it needs a reason."""
_ADVISORY_ID = re.compile(r"adv_[0-9a-f]{12}")
_FAILURE_ID = re.compile(r"AIF-[0-9a-f]{1,64}")
_BLOB_KEY = re.compile(BLOB_KEY_PATTERN)
_CASE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$"
_NAME_PUNCTUATION = frozenset(" .'-_")
_STATUS_ERRORS: Final = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    413: "too_large",
    429: "too_many_attempts",
}

type RuntimeFactory = Callable[..., Awaitable[Runtime]]
"""``(settings)``; with ``hosted`` on, ``(settings, meter=StoreMeter)``."""
type RegistryFactory = Callable[
    [Settings, "Store", Runtime, "StoreMeter", "AccessCache"], "TenantRegistry"
]


# --- API-only response and request bodies -----------------------------------------------


class Health(TephraModel):
    ok: bool
    mode: RunMode


class FeedList(TephraModel):
    feeds: list[FeedHealth]


class ReplayCaseSummary(TephraModel):
    """A recorded case without its record list (``GET /api/replays``)."""

    case_id: str
    label: str
    recorded_from: UtcDatetime
    recorded_to: UtcDatetime
    region: str
    volcano_ids: list[str]
    notes: str | None = None
    record_count: int
    banner: str
    synthetic: bool = False

    @classmethod
    def of(cls, case: ReplayCase) -> Self:
        return cls(
            case_id=case.case_id,
            label=case.label,
            recorded_from=case.recorded_from,
            recorded_to=case.recorded_to,
            region=case.region,
            volcano_ids=case.volcano_ids,
            notes=case.notes,
            record_count=len(case.records),
            banner=replay_banner(case),
            synthetic=case.synthetic,
        )


class ReplayCaseList(TephraModel):
    cases: list[ReplayCaseSummary]


@dataclass(frozen=True, slots=True)
class ReplayCatalogue:
    """``GET /api/replays``, built once per app: the manifests are part of the image and
    nothing writes them while the server runs, and validating them takes real CPU."""

    cases: list[ReplayCaseSummary]
    """Newest ``recorded_from`` first, as :func:`list_cases` orders them"""
    body: bytes
    etag: str

    @classmethod
    def build(cls, data_dir: Path) -> Self:
        cases = [ReplayCaseSummary.of(case) for case in list_cases(data_dir)]
        body = ReplayCaseList(cases=cases).model_dump_json().encode()
        return cls(cases=cases, body=body, etag=f'"{sha256_bytes(body)}"')


class ModeRequest(TephraModel):
    mode: RunMode
    case_id: str | None = Field(default=None, pattern=_CASE_ID_PATTERN)


class VisitorRequest(TephraModel):
    name: str | None = Field(default=None, max_length=64)


class AuditVerify(TephraModel):
    """``GET /api/audit/verify``: the chain's head as this instance last verified it."""

    intact: bool
    entries: int
    head_seq: int
    head_sha256: str
    checked_at: UtcDatetime
    problems: list[str] = Field(description="The first five, when any")
    note: str = Field(description="What the check covered")

    @classmethod
    def of(cls, head: ChainHead) -> Self:
        return cls(
            intact=head.intact,
            entries=head.entries,
            head_seq=head.seq,
            head_sha256=head.sha256,
            checked_at=head.checked_at,
            problems=head.problems[:5],
            note=AUDIT_VERIFY_NOTE,
        )


# --- dependencies -----------------------------------------------------------------------


def _tenant_runtime(scope: TenantScope) -> Runtime:
    runtime = scope.runtime
    if runtime is None:
        raise ApiError(409, "not_started", f"TEPHRA has not started for {scope.name} yet")
    return runtime


def get_runtime(request: Request, scope: TenantScopeDep) -> Runtime:
    """The airline's runtime under ``/a/<ICAO>/api``, else the site's own."""
    if scope is not None:
        return _tenant_runtime(scope)
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    return runtime


def get_app_settings(request: Request, scope: TenantScopeDep) -> Settings:
    """The airline runtime's settings under ``/a/<ICAO>/api``, else the site's."""
    if scope is not None:
        return _tenant_runtime(scope).settings
    settings: Settings = request.app.state.settings
    return settings


def get_replay_catalogue(request: Request) -> ReplayCatalogue:
    catalogue: ReplayCatalogue | None = getattr(request.app.state, "replays", None)
    if catalogue is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    return catalogue


RuntimeDep = Annotated[Runtime, Depends(get_runtime)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
ReplaysDep = Annotated[ReplayCatalogue, Depends(get_replay_catalogue)]
DeskSession = Annotated[SessionInfo, Depends(require_desk)]
"""The Desk's session, or under ``/a/<ICAO>/api`` the member's (``auth.require_desk``)."""
Limit = Annotated[int, Query(ge=1, le=200)]


def _json(
    model: BaseModel, status_code: int = 200, headers: Mapping[str, str] | None = None
) -> Response:
    return Response(
        content=model.model_dump_json(),
        status_code=status_code,
        media_type="application/json",
        headers=dict(headers or {}),
    )


def _actor(session: SessionInfo) -> str:
    return actor_of(session)


def _check_advisory_id(advisory_id: str) -> None:
    if _ADVISORY_ID.fullmatch(advisory_id) is None:
        raise ApiError(404, "not_found", "No such advisory")


def _desk_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not 2 <= len(name) <= 32 or not all(ch.isalnum() or ch in _NAME_PUNCTUATION for ch in name):
        raise ApiError(
            422,
            "validation_failed",
            "Invalid dispatcher name",
            problems=["name: 2 to 32 letters, digits, spaces or . ' - _"],
        )
    return name


# --- health ---------------------------------------------------------------------------

health = APIRouter()


@health.get("/health", response_model=Health)
@health.get("/healthz", response_model=Health)
async def healthz(runtime: RuntimeDep) -> Response:
    """``/health`` is the one to probe on Cloud Run, whose front end answers ``/healthz``
    itself with a 404 (Google reserves URL paths ending in z); ``/healthz`` stays for local
    runs and other hosts."""
    return _json(Health(ok=True, mode=runtime.mode))


# --- read API (public, read-only) -------------------------------------------------------

read_api = APIRouter(prefix="/api")


@read_api.get("/state", response_model=SystemState)
async def get_state(runtime: RuntimeDep) -> Response:
    return _json(await runtime.system_state())


WALL_ADVISORIES: Final = 50
WALL_TRACE: Final = 200
"""The trace steps GET /api/wall sends: all the bus keeps per event (EventBus's history) and the
Wall's own TRACE_KEEP."""


async def _wall_advisories(runtime: Runtime) -> list[Advisory]:
    """Every open draft of the mode playing (the Wall counts them per volcano), then that mode's
    newest other advisories, 50 in all unless the drafts alone are more. In REPLAY `created_at`
    follows a clock that loops, so the newest 50 of the whole store can be an earlier run's (or
    the other mode's) and hide this run's drafts."""
    replay = runtime.mode is RunMode.REPLAY
    drafts = [
        advisory
        for advisory in await approvals.list_advisories(
            runtime.store, status=AdvisoryStatus.DRAFT, limit=OPEN_DRAFT_LIMIT
        )
        if advisory.replay == replay
    ]
    room = max(0, WALL_ADVISORIES - len(drafts))
    recent = await approvals.list_advisories(runtime.store, limit=WALL_ADVISORIES * 4)
    others = [a for a in recent if a.replay == replay and a.status is not AdvisoryStatus.DRAFT]
    return [*drafts, *others[:room]]


@read_api.get("/wall", response_model=WallResponse)
async def get_wall(runtime: RuntimeDep) -> Response:
    state, snapshot, advisories = await asyncio.gather(
        runtime.system_state(),
        runtime.wall_snapshot(),
        _wall_advisories(runtime),
    )
    # every trace step the bus keeps (one stub run alone writes about 100): the demo's catch-up
    # plays the newest whole chain of steps, from a feed read to You decide
    trace = [
        TraceEvent.model_validate(event.data)
        for event in runtime.bus.recent(SseEvent.TRACE, limit=WALL_TRACE)
    ]
    return _json(WallResponse(state=state, snapshot=snapshot, advisories=advisories, trace=trace))


@read_api.get("/advisories", response_model=AdvisoryList)
async def get_advisories(
    runtime: RuntimeDep, status: AdvisoryStatus | None = None, limit: Limit = 50
) -> Response:
    advisories = await approvals.list_advisories(runtime.store, status=status, limit=limit)
    return _json(AdvisoryList(advisories=advisories))


@read_api.get("/audit", response_model=AuditList)
async def get_audit(
    runtime: RuntimeDep,
    advisory_id: Annotated[str | None, Query(pattern=r"^adv_[0-9a-f]{12}$")] = None,
    limit: Limit = 100,
) -> Response:
    entries = await audit.list_entries(runtime.store, advisory_id=advisory_id, limit=limit)
    return _json(AuditList(entries=entries))


@read_api.get("/audit/verify", response_model=AuditVerify)
async def get_audit_verify(runtime: RuntimeDep) -> Response:
    """Public: the count and hash of the audit chain's head, and whether the walk from the
    first entry on this instance found it intact (``tephra.desk.audit``)."""
    head = runtime.audit_head
    if head is None:
        raise ApiError(503, "starting", "The audit chain has not been checked yet")
    return _json(AuditVerify.of(head))


@read_api.get("/outbound", response_model=OutboundList)
async def get_outbound(runtime: RuntimeDep, limit: Limit = 50) -> Response:
    docs = await runtime.store.list_docs(
        Collection.OUTBOUND, limit=limit, order_by="queued_wall_at", descending=True
    )
    messages = [OutboundMessage.model_validate(doc) for doc in docs]
    return _json(OutboundList(messages=messages))


@read_api.get("/feeds", response_model=FeedList)
async def get_feeds(runtime: RuntimeDep) -> Response:
    state = await runtime.system_state()
    return _json(FeedList(feeds=state.feeds))


@read_api.get("/policy", response_model=PolicyResponse)
async def get_policy(runtime: RuntimeDep) -> Response:
    summary = runtime.policy_summary
    return _json(PolicyResponse(policy=runtime.policy, policy_hash=summary.policy_hash))


@read_api.get("/replays", response_model=ReplayCaseList)
async def get_replays(request: Request, catalogue: ReplaysDep) -> Response:
    # no-cache, not no-store: the browser keeps the list and revalidates it with the ETag.
    headers = {"ETag": catalogue.etag, "Cache-Control": "no-cache"}
    if _etag_matches(request.headers.get("if-none-match"), catalogue.etag):
        return Response(status_code=304, headers=headers)
    return Response(content=catalogue.body, media_type="application/json", headers=headers)


def _etag_matches(header: str | None, etag: str) -> bool:
    """``If-None-Match`` uses the weak comparison: ``W/`` is ignored, ``*`` matches."""
    if header is None:
        return False
    tags = {tag.strip().removeprefix("W/") for tag in header.split(",")}
    return "*" in tags or etag in tags


@read_api.get(
    "/blobs/{key:path}",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
async def get_blob(key: str, runtime: RuntimeDep) -> Response:
    if _BLOB_KEY.fullmatch(key) is None:
        raise ApiError(404, "not_found", "No such image")
    found = await runtime.store.get_blob(key)
    if found is None:
        raise ApiError(404, "not_found", "No such image")
    data, _ = found
    # Blob keys carry the scan time, so a key's bytes never change.
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400, immutable"},
    )


_ICAO: Final = re.compile(r"[A-Z0-9]{4}")


@read_api.get("/routes/{origin_icao}/{dest_icao}")
async def get_route_line(origin_icao: str, dest_icao: str, runtime: RuntimeDep) -> Response:
    """The great circle between two airports, for the route of the flight picked on the Wall.

    Which airports a flight flies between comes from ``AircraftFeatureProps`` (code, VRS
    standing data); this answer depends only on the two positions, so the browser caches it.
    """
    if (
        _ICAO.fullmatch(origin_icao) is None
        or _ICAO.fullmatch(dest_icao) is None
        or origin_icao == dest_icao
    ):
        raise ApiError(404, "not_found", "No such route")
    table, airports = runtime.routes, runtime.airports
    if table.position(origin_icao, airports) is None or table.position(dest_icao, airports) is None:
        raise ApiError(404, "not_found", "Airport position not known")
    body = route_features({(origin_icao, dest_icao): ()}, table, airports)
    return Response(
        content=json.dumps(body, separators=(",", ":")),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@read_api.get("/airports")
async def get_airports(runtime: RuntimeDep) -> Response:
    """The airport catalogue as GeoJSON points, for the maps: where an airport the plan closes is.

    The catalogue is the shipped OurAirports extract, so it changes only with a deploy.
    """
    features = [
        {
            "type": "Feature",
            "id": airport.icao,
            "geometry": {"type": "Point", "coordinates": [airport.lon, airport.lat]},
            "properties": {
                "icao": airport.icao,
                "iata": airport.iata,
                "name": airport.name,
                "country": airport.country,
                "longest_runway_m": airport.longest_runway_m,
            },
        }
        for airport in runtime.airports.all()
    ]
    return Response(
        content=json.dumps(
            {"type": "FeatureCollection", "features": features}, separators=(",", ":")
        ),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@read_api.get("/events", response_class=StreamingResponse)
@read_api.get("/stream", response_class=StreamingResponse, include_in_schema=False)
async def get_events(
    request: Request, runtime: RuntimeDep, scope: TenantScopeDep
) -> StreamingResponse:
    """The demo's streams share ``event_streams``. An airline's stream takes one of that
    airline's own places (``hosted_streams_per_tenant``, set apart from the demo's, so no
    number of demo visitors can cut an airline off) and one of its member's
    (``TENANT_STREAMS_PER_MEMBER``). It ends after 15 minutes, and within 15 s of its reader
    losing the airline: removed, a new role, signed out everywhere, or the airline suspended
    or stopped (the page reopens)."""
    if scope is None:
        held = [request.app.state.event_streams]
    else:
        held = [_tenant_streams(request, scope.icao), _member_streams(request, scope)]
    taken: list[StreamSlots] = []
    for slots in held:
        if not slots.acquire():
            for other in taken:
                other.release()
            raise ApiError(
                503,
                "too_many_streams",
                "Too many open event streams; try again shortly",
                headers={"Retry-After": str(STREAMS_RETRY_AFTER_S)},
            )
        taken.append(slots)
    stream = event_stream(
        runtime.bus,
        last_event_id=parse_last_event_id(request.headers.get("last-event-id")),
        mode=lambda: runtime.mode,
        **({} if scope is None else _tenant_stream_rules(request, scope, runtime)),
    )
    return EventStreamResponse(stream, *held)


def _tenant_streams(request: Request, icao: str) -> StreamSlots:
    streams: dict[str, StreamSlots] = request.app.state.tenant_streams
    if icao not in streams:
        streams[icao] = StreamSlots(request.app.state.settings.hosted_streams_per_tenant)
    return streams[icao]


def _member_streams(request: Request, scope: TenantScope) -> StreamSlots:
    streams: dict[tuple[str, str], StreamSlots] = request.app.state.member_streams
    key = (scope.icao, scope.login_key or "")
    if key not in streams:
        streams[key] = StreamSlots(TENANT_STREAMS_PER_MEMBER)
    return streams[key]


def demo_stream_places(settings: Settings) -> int:
    """The demo's open streams: all of ``max_event_streams``, less, with ``hosted`` on, every
    airline's own places (the config check keeps at least one for the demo)."""
    if "hosted" not in settings.features:
        return settings.max_event_streams
    held_apart = settings.hosted_max_tenants * settings.hosted_streams_per_tenant
    return settings.max_event_streams - held_apart


def _tenant_stream_rules(request: Request, scope: TenantScope, runtime: Runtime) -> dict[str, Any]:
    registry: TenantRegistry = request.app.state.registry
    access: AccessCache = request.app.state.access
    root: Store = request.app.state.runtime.store
    login_key, version = scope.login_key, scope.version
    assert login_key is not None, "a member's scope names its login"
    assert version is not None, "a member's scope names its session version"

    async def still_allowed() -> bool:
        handle = registry.handle(scope.icao)
        if handle is None or handle.runtime is not runtime or handle.record.state not in RUN:
            return False
        member = await access.member(root, login_key, version, scope.icao, record=handle.record)
        return member is not None and member.role == scope.role

    return {
        "lifetime_s": TENANT_STREAM_LIFETIME_S,
        "check": still_allowed,
        "check_every_s": TENANT_STREAM_CHECK_S,
    }


# --- desk (dispatcher session) ----------------------------------------------------------

desk_api = APIRouter(prefix="/api")


@desk_api.post(
    "/desk/login",
    response_model=SessionInfo,
    dependencies=[Depends(require_csrf), Depends(require_desk_enabled)],
)
async def login(
    body: LoginRequest, request: Request, runtime: RuntimeDep, settings: SettingsDep
) -> Response:
    throttle: LoginThrottle = request.app.state.login_throttle
    client = client_key(request)
    if throttle.blocked(client):
        retry_after = throttle.retry_after_s(client)
        raise ApiError(
            429,
            "too_many_attempts",
            "Too many failed logins; try again later",
            headers={"Retry-After": str(retry_after)},
        )
    name = _desk_name(body.name)
    if not pin_matches(body.pin, settings):
        throttle.record_failure(client)
        await audit.record(
            runtime.store,
            actor=f"desk:{name}",
            action=AuditAction.LOGIN_FAILED,
            note="wrong PIN",
        )
        raise ApiError(401, "bad_pin", "Wrong PIN")
    throttle.clear(client)
    sid = new_session_id()
    token, expires_at = sign_session(name, settings, at=wall_clock_now(), sid=sid)
    await audit.record(runtime.store, actor=f"desk:{name}", action=AuditAction.LOGIN_OK)
    response = _json(SessionInfo(name=name, expires_at=expires_at, sid=sid))
    set_session_cookie(response, token, settings, secure=is_https(request))
    return response


@desk_api.post(
    "/desk/visitor",
    response_model=SessionInfo,
    dependencies=[Depends(require_csrf), Depends(require_desk_enabled)],
)
async def enter_as_visitor(
    body: VisitorRequest, request: Request, runtime: RuntimeDep, settings: SettingsDep
) -> Response:
    """A visitor session without a PIN, only while a replay plays and the server allows it.
    Every decision it makes is audited as ``visitor:<name>`` and capped per session."""
    if settings.visitor_access != "replay" or runtime.mode is not RunMode.REPLAY:
        raise ApiError(503, "visitor_off", "Visitor access is switched off on this server.")
    throttle: LoginThrottle = request.app.state.visitor_throttle
    client = client_key(request)
    if throttle.blocked(client):
        raise ApiError(
            429,
            "too_many_visitors",
            "Too many visitor sessions from this address; try again later",
            headers={"Retry-After": str(throttle.retry_after_s(client))},
        )
    throttle.record_failure(client)  # every mint counts, not only a refused one
    name = _desk_name(body.name) if body.name else f"Visitor-{secrets.token_hex(2)}"
    sid = new_session_id()
    token, expires_at = sign_session(name, settings, at=wall_clock_now(), role="visitor", sid=sid)
    session = SessionInfo(name=name, expires_at=expires_at, role="visitor", sid=sid)
    await audit.record(runtime.store, actor=_actor(session), action=AuditAction.VISITOR_ENTERED)
    response = _json(session)
    set_session_cookie(response, token, settings, secure=is_https(request), role="visitor")
    return response


@desk_api.post("/desk/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(request: Request) -> Response:
    response = Response(status_code=204)
    clear_session_cookie(response, secure=is_https(request))
    return response


@desk_api.get("/desk/me", response_model=SessionInfo)
async def desk_me(session: DeskSession) -> Response:
    return _json(session)


@desk_api.get("/desk/advisories", response_model=AdvisoryList)
async def desk_advisories(
    session: DeskSession,
    runtime: RuntimeDep,
    status: AdvisoryStatus = AdvisoryStatus.DRAFT,
    limit: Limit = 50,
) -> Response:
    advisories = await approvals.list_advisories(runtime.store, status=status, limit=limit)
    return _json(AdvisoryList(advisories=advisories))


@desk_api.post(
    "/desk/advisories/{advisory_id}/approve",
    response_model=Advisory,
    dependencies=[Depends(require_csrf)],
)
async def approve_advisory(
    advisory_id: str, body: DecisionRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_advisory_id(advisory_id)
    reason, note = await _crew_reason(runtime, advisory_id, body.reason)

    async def decide(cone_id: str | None) -> Advisory:
        return await approvals.approve(
            runtime.store,
            runtime.bus,
            advisory_id,
            expected_version=body.version,
            actor=_actor(session),
            reason=reason,
            note=note,
            current_cone_id=cone_id,
        )

    return _json(await _decide_against_now(runtime, advisory_id, decide))


@desk_api.post(
    "/desk/advisories/{advisory_id}/edit",
    response_model=Advisory,
    dependencies=[Depends(require_csrf)],
)
async def edit_advisory(
    advisory_id: str, body: EditRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_advisory_id(advisory_id)
    reason, note = await _crew_reason(runtime, advisory_id, body.reason)

    async def decide(cone_id: str | None) -> Advisory:
        return await approvals.edit_and_approve(
            runtime.store,
            runtime.bus,
            advisory_id,
            expected_version=body.version,
            body=body.body,
            actor=_actor(session),
            reason=reason,
            note=note,
            current_cone_id=cone_id,
        )

    return _json(await _decide_against_now(runtime, advisory_id, decide))


async def _decide_against_now(
    runtime: Runtime, advisory_id: str, decide: Callable[[str | None], Awaitable[Advisory]]
) -> Advisory:
    """Queue a draft against the situation now: ``decide`` gets the id of the ash area held
    for the draft's volcano, so a draft written for an older area is refused
    (``cone_changed``, 409). The id is read from ``cones/<volcano_id>``, which the pipeline
    writes on every change of its cone; None when the server cannot say (no such draft, a
    draft of the other mode, no cone held). A refusal is one trace line on the Wall (stage
    DESK, by code) before the handler answers; a missing draft is the decision's own 404."""
    advisory = await approvals.get_advisory(runtime.store, advisory_id)
    cone_id = None
    if advisory is not None and advisory.replay == (runtime.mode is RunMode.REPLAY):
        doc = await runtime.store.get(Collection.CONES, advisory.volcano_id)
        held = None if doc is None else doc.get("id")
        cone_id = held if isinstance(held, str) else None
    try:
        return await decide(cone_id)
    except approvals.RuleBlocked as exc:
        flight = advisory_id if advisory is None else advisory.proxy_flight
        runtime.trace(
            TraceStage.DESK,
            "code",
            f"{flight}: approval refused: {exc.problems[0]}",
            level="warn",
            volcano_id=None if advisory is None else advisory.volcano_id,
            flight_id=None if advisory is None else advisory.flight_id,
        )
        raise


async def _crew_reason(
    runtime: Runtime, advisory_id: str, given: str | None
) -> tuple[str | None, str | None]:
    """``(reason, audit note)``. Approving a CONTINUE or MONITOR for a flight whose projected
    track crosses an active crew report area needs a written reason; every tracked flight is
    airborne (ADS-B ground targets are dropped). Other approvals keep a reason if one is
    given. A missing advisory is left to the decision itself (404)."""
    reason = " ".join((given or "").split()) or None
    advisory = await approvals.get_advisory(runtime.store, advisory_id)
    if advisory is None or advisory.action not in REASON_ACTIONS:
        return reason, None
    if advisory.replay != (runtime.mode is RunMode.REPLAY):
        return reason, None
    flag = runtime.crew_flag(advisory.hex)
    if flag is None:
        return reason, None
    if reason is None or len(reason) < approvals.MIN_CREW_REASON_CHARS:
        raise ApiError(
            422,
            "reason_required",
            f"{flag.line}: approving {advisory.action.value} needs a written reason",
            problems=[f"reason: at least {approvals.MIN_CREW_REASON_CHARS} characters"],
        )
    return reason, f"{flag.line} ({', '.join(flag.report_ids)}): reason given"


@desk_api.post(
    "/desk/advisories/{advisory_id}/reject",
    response_model=Advisory,
    dependencies=[Depends(require_csrf)],
)
async def reject_advisory(
    advisory_id: str, body: RejectRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_advisory_id(advisory_id)
    advisory = await approvals.reject(
        runtime.store,
        runtime.bus,
        advisory_id,
        expected_version=body.version,
        reason=body.reason.strip(),
        actor=_actor(session),
    )
    return _json(advisory)


@desk_api.get("/desk/ai-failures", response_model=AiFailureList)
async def desk_ai_failures(
    session: DeskSession, runtime: RuntimeDep, open_only: bool = True, limit: Limit = 50
) -> Response:
    """Flights the AI could not plan or draft for, in the current mode (in REPLAY, the run
    playing)."""
    listed = await failures.list_failures(
        runtime.store,
        open_only=open_only,
        replay=runtime.mode is RunMode.REPLAY,
        run_since=runtime.replay_run_since,
        limit=limit,
    )
    return _json(AiFailureList(failures=listed))


@desk_api.post(
    "/desk/ai-failures/{failure_id}/handled",
    response_model=AiFailure,
    dependencies=[Depends(require_csrf)],
)
async def handle_ai_failure(
    failure_id: str, body: HandledRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    if _FAILURE_ID.fullmatch(failure_id) is None:
        raise ApiError(404, "not_found", "No such AI failure")
    try:
        handled = await failures.mark_handled(
            runtime.store, runtime.bus, failure_id, actor=_actor(session), note=body.note
        )
    except failures.FailureNotFound:
        raise ApiError(404, "not_found", "No such AI failure") from None
    return _json(handled)


@desk_api.post("/mode", response_model=SystemState, dependencies=[Depends(require_csrf)])
async def switch_mode(
    body: ModeRequest,
    session: DeskSession,
    runtime: RuntimeDep,
    settings: SettingsDep,
    # A plain default, not Annotated: only a switch that names no case reads the catalogue.
    catalogue: ReplayCatalogue = Depends(get_replay_catalogue),
) -> Response:
    before = _mode_facts(runtime)
    if body.mode is RunMode.REPLAY:
        case = await _replay_case_for(body.case_id, runtime, settings, catalogue)
        # the case is set under its lock; a tick in progress is stopped, not waited for
        await runtime.switch_mode(body.mode, case=case, preempt=True)
    else:
        await runtime.switch_mode(body.mode, preempt=True)
    await audit.record(
        runtime.store,
        actor=_actor(session),
        action=AuditAction.MODE_SWITCH,
        before=before,
        after=_mode_facts(runtime),
        note="switched from the desk",
    )
    return _json(await runtime.system_state())


def _mode_facts(runtime: Runtime) -> dict[str, Any]:
    case = runtime.replay_case
    return {"mode": runtime.mode.value, "case_id": case.case_id if case else None}


async def _replay_case_for(
    case_id: str | None, runtime: Runtime, settings: Settings, catalogue: ReplayCatalogue
) -> ReplayCase:
    if case_id is None:
        if runtime.replay_case is not None:
            return runtime.replay_case
        if not catalogue.cases:
            raise ApiError(409, "invalid_transition", "No replay case has been recorded")
        case_id = catalogue.cases[0].case_id
    try:
        return await asyncio.to_thread(load_case, settings.data_dir, case_id)
    except (OSError, ValueError) as exc:
        raise ApiError(404, "not_found", "No such replay case") from exc


# --- scheduler task ---------------------------------------------------------------------

tasks = APIRouter()


@tasks.post("/tasks/tick", response_model=TickReport, dependencies=[Depends(require_task_token)])
async def run_tick(request: Request, runtime: RuntimeDep) -> Response:
    """The demo's tick. With hosted airlines, their pass is started first and runs on its own,
    so a slow demo tick never delays them (and theirs never delays this answer)."""
    registry: TenantRegistry | None = getattr(request.app.state, "registry", None)
    if registry is not None:
        registry.kick()
    return _json(await runtime.tick(reason="scheduler"))


# --- errors -----------------------------------------------------------------------------


def _install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> Response:
        return _json(exc.body(), exc.status_code, exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> Response:
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        body = ErrorBody(error=_STATUS_ERRORS.get(exc.status_code, "error"), detail=detail)
        return _json(body, exc.status_code, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> Response:
        # Only locations and messages: the input itself may be a PIN.
        problems = [
            f"{'.'.join(str(part) for part in error.get('loc', ()) if part != 'body')}: "
            f"{error.get('msg', 'invalid')}"
            for error in exc.errors()
        ]
        body = ErrorBody(error="validation_failed", detail="Request is invalid", problems=problems)
        return _json(body, 422)

    @app.exception_handler(approvals.VersionConflict)
    async def version_conflict(_: Request, exc: approvals.VersionConflict) -> Response:
        body = ErrorBody(
            error="version_conflict",
            detail="The advisory changed since you loaded it",
            current=exc.current,
        )
        return _json(body, 409)

    @app.exception_handler(approvals.InvalidTransition)
    async def invalid_transition(_: Request, exc: approvals.InvalidTransition) -> Response:
        detail = str(exc) or "Only a DRAFT advisory can be decided"
        return _json(ErrorBody(error="invalid_transition", detail=detail), 409)

    @app.exception_handler(approvals.AdvisoryNotFound)
    async def advisory_not_found(_: Request, exc: approvals.AdvisoryNotFound) -> Response:
        return _json(ErrorBody(error="not_found", detail="No such advisory"), 404)

    @app.exception_handler(approvals.RuleBlocked)
    async def rule_blocked(_: Request, exc: approvals.RuleBlocked) -> Response:
        body = ErrorBody(error=exc.code, detail=exc.problems[0], problems=exc.problems)
        return _json(body, 409)

    @app.exception_handler(approvals.EditRejected)
    async def edit_rejected(_: Request, exc: approvals.EditRejected) -> Response:
        body = ErrorBody(
            error="validation_failed", detail="Edited body rejected", problems=exc.problems
        )
        return _json(body, 422)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> Response:
        logger.error(
            "unhandled error",
            exc_info=exc,
            extra={"json_fields": {"path": request.url.path, "method": request.method}},
        )
        response = _json(ErrorBody(error="internal", detail="Internal error"), 500)
        # Starlette sends this response from outside every middleware, HttpGuardMiddleware too.
        _add_security_headers(response.headers, path=request.url.path, https=is_https(request))
        return response


# --- middleware -------------------------------------------------------------------------


class HttpGuardMiddleware:
    """Security headers on every response, a request-body cap and one access-log line.

    Pure ASGI rather than ``BaseHTTPMiddleware`` so the SSE stream is not buffered.
    """

    def __init__(self, app: ASGIApp, *, upload_bytes: int | None = None) -> None:
        self.app = app
        self.upload_bytes = upload_bytes or MAX_BODY_BYTES

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.perf_counter()
        status = 500
        request_headers = Headers(scope=scope)
        https = scope.get("scheme") == "https" or request_headers.get(
            "x-forwarded-proto", ""
        ).lower().startswith("https")
        path: str = scope.get("path", "")
        _request_trace.set(request_trace(request_headers))

        async def guarded_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = list(message.get("headers", []))
                _add_security_headers(MutableHeaders(scope=message), path=path, https=https)
            await send(message)

        limit = self._limit(path)
        try:
            if _body_too_large(request_headers, limit):
                body = ErrorBody(error="too_large", detail="Request body too large")
                await _json(body, 413)(scope, receive, guarded_send)
            else:
                await self.app(scope, _capped(receive, limit), guarded_send)
        finally:
            _log_request(scope, status, time.perf_counter() - started)

    def _limit(self, path: str) -> int:
        """A recording may be about a megabyte, a pasted notice a few dozen kilobytes, an
        airline's answers up to 128 KiB and a push (sent, uploaded or dry-run) up to 512 KiB."""
        if path == VOICE_PATH:
            return self.upload_bytes
        if path == NOTICE_PATH:
            return MAX_NOTICE_BODY_BYTES
        if path in ONBOARD_PATHS:
            return MAX_ONBOARD_BODY_BYTES
        if path in PUSH_BODY_PATHS:
            return MAX_PUSH_BODY_BYTES
        return MAX_BODY_BYTES


def _add_security_headers(headers: MutableHeaders, *, path: str, https: bool) -> None:
    if path == DESK_PATH:
        headers["permissions-policy"] = DESK_PERMISSIONS_POLICY
    for name, value in SECURITY_HEADERS.items():
        headers.setdefault(name, value)
    headers.setdefault("cache-control", "no-store" if path.startswith("/api/") else "no-cache")
    if https:
        headers.setdefault("strict-transport-security", "max-age=31536000")


def _body_too_large(headers: Headers, limit: int) -> bool:
    length = headers.get("content-length")
    return length is not None and (not length.isdigit() or int(length) > limit)


def _capped(receive: Receive, limit: int) -> Receive:
    """Count the body as it streams in: a chunked request carries no Content-Length."""
    received = 0

    async def capped_receive() -> Message:
        nonlocal received
        message = await receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise StarletteHTTPException(413, "Request body too large")
        return message

    return capped_receive


@dataclass(frozen=True, slots=True)
class RequestTrace:
    """The trace Cloud Run's front end stamps on a request, so every log line of the request
    joins it in Cloud Trace. ``span_id`` is 16 hex digits; ``sampled`` is the trace flag."""

    trace_id: str
    span_id: str | None = None
    sampled: bool = False


_request_trace: contextvars.ContextVar[RequestTrace | None] = contextvars.ContextVar(
    "tephra_request_trace", default=None
)


def request_trace(headers: Headers) -> RequestTrace | None:
    """``X-Cloud-Trace-Context`` (``TRACE_ID/SPAN_ID;o=1``, the span decimal) first, then W3C
    ``traceparent``; a malformed header is ignored."""
    cloud = _CLOUD_TRACE.match(headers.get(CLOUD_TRACE_HEADER, "").strip())
    if cloud is not None:
        trace_id, span, flag = cloud.groups()
        span_id = None if span is None else format(int(span) & 0xFFFFFFFFFFFFFFFF, "016x")
        return RequestTrace(trace_id.lower(), span_id, flag == "1")
    w3c = _TRACEPARENT.match(headers.get(TRACEPARENT_HEADER, "").strip())
    if w3c is not None:
        trace_id, span_id, flags = w3c.groups()
        return RequestTrace(trace_id.lower(), span_id.lower(), bool(int(flags, 16) & 1))
    return None


def _log_request(scope: Scope, status: int, elapsed_s: float) -> None:
    path: str = scope.get("path", "")
    level = logging.DEBUG if path in {"/health", "/healthz"} else logging.INFO
    fields = {
        "httpRequest": {
            "requestMethod": scope.get("method", ""),
            "requestUrl": path,
            "status": status,
            "latency": f"{elapsed_s:.3f}s",
        }
    }
    logging.getLogger("tephra.api.access").log(
        level, "%s %s %d", scope.get("method", ""), path, status, extra={"json_fields": fields}
    )


# --- logging ----------------------------------------------------------------------------


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line, in the shape Cloud Logging reads (``severity``, ``message``).

    Extra structured fields are passed as ``extra={"json_fields": {...}}``. A line written
    while a request is handled carries that request's trace: with ``project`` set, the
    ``logging.googleapis.com/trace`` fields Cloud Logging joins to Cloud Trace; without one,
    a plain ``trace_id``.
    """

    def __init__(self, *, project: str | None = None) -> None:
        super().__init__()
        self.project = project

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "severity": record.levelname,
            "time": timeutil.to_iso(datetime.fromtimestamp(record.created, UTC)),
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "json_fields", None)
        if isinstance(fields, Mapping):
            entry.update(fields)
        tenant = current_tenant()
        if tenant is not None:
            entry.setdefault("tenant", tenant)
        entry.update(self._trace_fields(_request_trace.get()))
        if record.exc_info:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)

    def _trace_fields(self, trace: RequestTrace | None) -> dict[str, Any]:
        if trace is None:
            return {}
        if self.project is None:
            return {"trace_id": trace.trace_id}
        fields: dict[str, Any] = {
            "logging.googleapis.com/trace": f"projects/{self.project}/traces/{trace.trace_id}",
            "logging.googleapis.com/trace_sampled": trace.sampled,
        }
        if trace.span_id is not None:
            fields["logging.googleapis.com/spanId"] = trace.span_id
        return fields


def configure_logging(level: str, *, project: str | None = None) -> None:
    """Route every logger (uvicorn's included) through one JSON handler on stdout;
    ``project`` (the GCP project) makes the request trace fields Cloud Logging joins."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(project=project))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


# --- app factory ------------------------------------------------------------------------


def _lifespan(
    settings: Settings,
    runtime_factory: RuntimeFactory,
    registry_factory: RegistryFactory | None,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    hosted = "hosted" in settings.features

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.replays = await asyncio.to_thread(ReplayCatalogue.build, settings.data_dir)
        registry: TenantRegistry | None = None
        if hosted:
            meter = _new_meter(settings)
            runtime = await runtime_factory(settings, meter=meter)
            app.state.runtime = runtime
            await meter.restore(runtime.store)
            app.state.meter = meter
            factory = registry_factory or _default_registry
            registry = factory(settings, runtime.store, runtime, meter, app.state.access)
            await registry.start_all()
            app.state.registry = registry
        else:
            runtime = await runtime_factory(settings)
            app.state.runtime = runtime
        watchdog = asyncio.create_task(run_writer_watchdog(runtime), name="tephra-writer-watchdog")
        watchdog.add_done_callback(_report_task_exit)
        stop = asyncio.Event()
        scheduler: asyncio.Task[None] | None = None
        if settings.local_scheduler:
            loop = (
                run_local_scheduler(runtime, stop)
                if registry is None
                else run_local_scheduler(runtime, stop, after_tick=registry.kick)
            )
            scheduler = asyncio.create_task(loop, name="tephra-local-scheduler")
            scheduler.add_done_callback(_report_task_exit)
        else:
            # Cloud Scheduler's first tick may be a minute away; the picture (official
            # polygons, cones, aircraft) is built now. An overlapping tick skips itself.
            scheduler = asyncio.create_task(_startup_tick(runtime), name="tephra-startup-tick")
        logger.info(
            "TEPHRA started",
            extra={
                "json_fields": {
                    "mode": runtime.mode.value,
                    "llm": settings.llm,
                    "store": settings.store,
                    "local_scheduler": settings.local_scheduler,
                    "desk_enabled": desk_enabled(settings),
                }
            },
        )
        try:
            yield
        finally:
            if registry is not None:
                # the airlines first: their runtimes, counters and stores close before the
                # demo's store (their root) does
                await registry.aclose()
                del app.state.registry
            stop.set()
            watchdog.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog
            if scheduler is not None:
                with suppress(TimeoutError, asyncio.CancelledError):
                    await asyncio.wait_for(scheduler, SCHEDULER_STOP_TIMEOUT_S)
            await runtime.aclose()
            del app.state.runtime
            del app.state.replays

    return lifespan


class PageFiles(StaticFiles):
    """The page files under ``/static``. Folders in ``hidden`` are never served from here: with
    ``hosted`` on that is ``kit/``, whose uploader leaves only through the member route. The check
    reads the path StaticFiles itself resolves (``//``, ``.`` and ``..`` already removed), case
    folded for a case-insensitive disk, so no spelling of the URL gets past it."""

    def __init__(self, *, hidden: frozenset[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.hidden = hidden

    async def get_response(self, path: str, scope: Scope) -> Response:
        top = path.replace(os.sep, "/").split("/", 1)[0].casefold()
        if top in self.hidden:
            raise StarletteHTTPException(404)
        return await super().get_response(path, scope)


def _new_meter(settings: Settings) -> "StoreMeter":
    from tephra.store.metered import StoreMeter

    return StoreMeter(blob_puts_cap=settings.hosted_blob_puts_cap)


def _default_registry(
    settings: Settings, root: "Store", demo: Runtime, meter: "StoreMeter", access: "AccessCache"
) -> "TenantRegistry":
    from tephra.hosted.registry import TenantRegistry

    return TenantRegistry(settings, root, demo, meter, access)


async def _startup_tick(runtime: Runtime) -> None:
    try:
        await runtime.tick(reason="startup")
    except Exception:  # a background task's error would otherwise vanish
        logger.exception("startup tick failed")


def _report_task_exit(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("%s stopped", task.get_name(), exc_info=exc)


def _include_feature_routers(app: FastAPI, dependencies: list[Any]) -> None:
    """The feature routers import the dependencies above, so they are imported here, not at the
    top of the module (a top-level import would be circular)."""
    from tephra.api import (
        routes_airline,
        routes_ask,
        routes_backtest,
        routes_chain,
        routes_comms,
        routes_connect,
        routes_crew,
        routes_duty,
        routes_evals,
        routes_notices,
        routes_recovery,
        routes_regdocs,
    )

    for module in (
        routes_ask,
        routes_notices,
        routes_recovery,
        routes_comms,
        routes_regdocs,
        routes_backtest,
        routes_duty,
        routes_crew,
        routes_connect,
        routes_chain,
        routes_evals,
        routes_airline,
    ):
        app.include_router(module.router, prefix="/api", dependencies=dependencies)


def _include_hosted_routers(app: FastAPI, dependencies: list[Any]) -> None:
    """Only with ``hosted`` on: the airline's own routes, the root hosted routes (set up,
    invites) and the operators' console and tasks."""
    from tephra.api import routes_admin, routes_hosted, routes_tenant
    from tephra.api.routes_pages import hosted_router as hosted_pages

    app.include_router(hosted_pages)
    app.include_router(routes_tenant.router, prefix="/api/tenant", dependencies=dependencies)
    app.include_router(routes_hosted.router, prefix="/api/hosted", dependencies=dependencies)
    app.include_router(routes_admin.router, prefix="/api/admin", dependencies=dependencies)
    app.include_router(routes_admin.tasks, dependencies=dependencies)


def _start_hosted_state(app: FastAPI) -> None:
    """Throttles and the access cache an airline request needs; the key variables leave the
    environment (B1). Nothing here reads the store."""
    from tephra.hosted.access import AccessCache
    from tephra.hosted.models import HostedRefused
    from tephra.hosted.throttles import HOSTED_THROTTLES

    @app.exception_handler(HostedRefused)
    async def hosted_refused(_: Request, exc: HostedRefused) -> Response:
        return _json(ErrorBody(error=exc.code, detail=exc.detail), exc.status)

    for name, (attempts, window_s) in HOSTED_THROTTLES.items():
        setattr(app.state, name, LoginThrottle(max_failures=attempts, window_s=window_s))
    app.state.access = AccessCache()
    app.state.tenant_streams = {}
    app.state.member_streams = {}
    for name in HOSTED_KEY_ENV:
        os.environ.pop(name, None)


def create_app(
    settings: Settings | None = None,
    *,
    runtime_factory: RuntimeFactory | None = None,
    registry_factory: RegistryFactory | None = None,
) -> FastAPI:
    """The TEPHRA app. ``runtime_factory`` defaults to ``create_runtime`` and
    ``registry_factory`` (hosted airlines, ``hosted`` on) to ``TenantRegistry`` (tests swap
    them). With ``hosted`` off nothing of hosting exists: no router, middleware or meter."""
    settings = settings if settings is not None else get_settings()
    hosted = "hosted" in settings.features
    app = FastAPI(
        title="TEPHRA",
        version=__version__,
        description="Volcanic-ash decision desk. Decision support only"
        + ("; the airline is fictional." if settings.airline.fictional else "."),
        lifespan=_lifespan(settings, runtime_factory or create_runtime, registry_factory),
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()
    app.state.visitor_throttle = LoginThrottle(
        max_failures=VISITOR_MINTS_PER_WINDOW, window_s=VISITOR_MINT_WINDOW_S
    )
    app.state.visitor_decisions = Counter[str]()
    for name, (attempts, window_s) in AIRLINE_THROTTLES.items():
        setattr(app.state, name, LoginThrottle(max_failures=attempts, window_s=window_s))
    app.state.event_streams = StreamSlots(demo_stream_places(settings))
    if hosted:
        _start_hosted_state(app)
    _install_error_handlers(app)
    # Starlette's GZip skips text/event-stream, images and woff2 by default, so the SSE stream is
    # never buffered or compressed. Added first so HttpGuard stays outermost and still sees every
    # response, including the 413 it sends itself.
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    app.add_middleware(HttpGuardMiddleware, upload_bytes=settings.max_upload_bytes)
    scoped: list[Any] = [Depends(tenant_scope)] if hosted else []
    if hosted:
        # outermost: HttpGuard's body limits and log line see the rewritten path
        app.add_middleware(TenantPathMiddleware)
    app.include_router(health)
    app.include_router(pages)
    app.include_router(read_api, dependencies=scoped)
    app.include_router(desk_api, dependencies=scoped)
    _include_feature_routers(app, scoped)
    app.include_router(tasks, dependencies=scoped)
    if hosted:
        _include_hosted_routers(app, scoped)
    hidden = frozenset({"kit"}) if hosted else frozenset()
    app.mount(
        "/static", PageFiles(directory=WEB_DIR, check_dir=False, hidden=hidden), name="static"
    )
    build_route_index(app)
    if hosted and (missing := scoped_routes_missing(app)):
        raise RuntimeError(f"routes without the airline check: {', '.join(missing)}")
    return app
