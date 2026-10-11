"""The FastAPI app: Wall and Desk pages, the read API, desk decisions, SSE and the tick task.

Routes and JSON shapes are the contract in MODULES.md section 8. Every body is a model from
``tephra.models`` dumped in JSON mode; every error is an ``ErrorBody`` and never carries a
stack trace or echoes request input. Nothing here calls an external system: approvals only
reach the ``outbound`` collection through ``tephra.desk.approvals``.
"""

import asyncio
import json
import logging
import re
import sys
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Final, Self

from fastapi import APIRouter, Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from tephra import __version__
from tephra.api import ApiError
from tephra.api.auth import (
    LoginThrottle,
    clear_session_cookie,
    client_key,
    desk_enabled,
    is_https,
    pin_matches,
    require_csrf,
    require_desk,
    require_desk_enabled,
    require_task_token,
    set_session_cookie,
    sign_session,
    wall_clock_now,
)
from tephra.api.sse import EventStreamResponse, StreamSlots, event_stream, parse_last_event_id
from tephra.config import MAX_BODY_BYTES, MAX_NOTICE_BODY_BYTES, Settings, get_settings
from tephra.desk import approvals, audit, failures
from tephra.models import (
    Advisory,
    AdvisoryList,
    AdvisoryStatus,
    AiFailure,
    AiFailureList,
    AuditAction,
    AuditList,
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
    UtcDatetime,
    WallResponse,
)
from tephra.pipeline import Runtime, create_runtime
from tephra.replay.cases import list_cases, load_case, replay_banner
from tephra.scheduler import run_local_scheduler, run_writer_watchdog
from tephra.store.base import BLOB_KEY_PATTERN, Collection
from tephra.util import timeutil
from tephra.util.hashing import sha256_bytes

__all__ = ["CONTENT_SECURITY_POLICY", "WEB_DIR", "configure_logging", "create_app"]

logger = logging.getLogger(__name__)

WEB_DIR: Final = Path(__file__).resolve().parent.parent / "web"
CONTENT_SECURITY_POLICY: Final = "; ".join(
    [
        "default-src 'self'",
        # Scripts only from the two pinned packages (docs/UI-DESIGN.md, THIRD_PARTY.md).
        "script-src 'self' https://unpkg.com/maplibre-gl@4.7.1/"
        " https://unpkg.com/@maplibre/maplibre-gl-compare@0.5.0/",
        "style-src 'self' https://unpkg.com",
        # Map tiles: OpenFreeMap basemap, NASA GIBS satellite context, Mapterhorn terrain.
        "img-src 'self' data: blob: https://tiles.openfreemap.org"
        " https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com",
        "connect-src 'self' https://tiles.openfreemap.org"
        " https://gibs.earthdata.nasa.gov https://tiles.mapterhorn.com",
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
SECURITY_HEADERS: Final = {
    "content-security-policy": CONTENT_SECURITY_POLICY,
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}
STREAMS_RETRY_AFTER_S: Final = 5
"""The Wall and the Desk reopen a refused event stream after 5 s on their own."""
SCHEDULER_STOP_TIMEOUT_S: Final = 10.0
GZIP_MIN_BYTES: Final = 1024
"""Responses smaller than this go out uncompressed; gzip would not pay for itself."""

_ADVISORY_ID = re.compile(r"adv_[0-9a-f]{12}")
_PRINT_DOC_ID = re.compile(r"(?:DOC-|ho_)[0-9a-f]{12}")
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

type RuntimeFactory = Callable[[Settings], Awaitable[Runtime]]


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


# --- dependencies -----------------------------------------------------------------------


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise ApiError(503, "starting", "TEPHRA is starting")
    return runtime


def get_app_settings(request: Request) -> Settings:
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
    return f"desk:{session.name}"


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


# --- pages ------------------------------------------------------------------------------

pages = APIRouter()


async def _page(filename: str) -> FileResponse:
    path = WEB_DIR / filename
    if not await asyncio.to_thread(path.is_file):
        raise ApiError(404, "not_found", "Page not installed")
    return FileResponse(path, media_type="text/html; charset=utf-8")


@pages.get("/", include_in_schema=False)
async def wall_page() -> FileResponse:
    return await _page("index.html")


@pages.get("/desk", include_in_schema=False)
async def desk_page() -> FileResponse:
    return await _page("desk.html")


@pages.get("/privacy", include_in_schema=False)
async def privacy_page() -> FileResponse:
    return await _page("privacy.html")


@pages.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> Response:
    """The live ash desk is a demo: no search engine should index or follow it."""
    return Response("User-agent: *\nDisallow: /\n", media_type="text/plain; charset=utf-8")


@pages.get("/docs/{doc_id}", include_in_schema=False)
async def doc_page(doc_id: str) -> FileResponse:
    """The printable page for an SRA/VAR draft (DOC-...) or a shift handover (ho_...). The page
    reads the id from the last path segment and fetches the JSON itself."""
    if _PRINT_DOC_ID.fullmatch(doc_id) is None:
        raise ApiError(404, "not_found", "No such document")
    return await _page("doc.html")


@pages.get("/healthz", response_model=Health)
async def healthz(runtime: RuntimeDep) -> Response:
    return _json(Health(ok=True, mode=runtime.mode))


# --- read API (public, read-only) -------------------------------------------------------

read_api = APIRouter(prefix="/api")


@read_api.get("/state", response_model=SystemState)
async def get_state(runtime: RuntimeDep) -> Response:
    return _json(await runtime.system_state())


@read_api.get("/wall", response_model=WallResponse)
async def get_wall(runtime: RuntimeDep) -> Response:
    state, snapshot, advisories = await asyncio.gather(
        runtime.system_state(),
        runtime.wall_snapshot(),
        approvals.list_advisories(runtime.store, limit=50),
    )
    trace = [
        TraceEvent.model_validate(event.data)
        for event in runtime.bus.recent(SseEvent.TRACE, limit=100)
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


@read_api.get("/events", response_class=StreamingResponse)
@read_api.get("/stream", response_class=StreamingResponse, include_in_schema=False)
async def get_events(request: Request, runtime: RuntimeDep) -> StreamingResponse:
    slots: StreamSlots = request.app.state.event_streams
    if not slots.acquire():
        raise ApiError(
            503,
            "too_many_streams",
            "Too many open event streams; try again shortly",
            headers={"Retry-After": str(STREAMS_RETRY_AFTER_S)},
        )
    stream = event_stream(
        runtime.bus,
        last_event_id=parse_last_event_id(request.headers.get("last-event-id")),
        mode=lambda: runtime.mode,
    )
    return EventStreamResponse(stream, slots)


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
    token, expires_at = sign_session(name, settings, at=wall_clock_now())
    await audit.record(runtime.store, actor=f"desk:{name}", action=AuditAction.LOGIN_OK)
    response = _json(SessionInfo(name=name, expires_at=expires_at))
    set_session_cookie(response, token, settings, secure=is_https(request))
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
    advisory = await approvals.approve(
        runtime.store,
        runtime.bus,
        advisory_id,
        expected_version=body.version,
        actor=_actor(session),
    )
    return _json(advisory)


@desk_api.post(
    "/desk/advisories/{advisory_id}/edit",
    response_model=Advisory,
    dependencies=[Depends(require_csrf)],
)
async def edit_advisory(
    advisory_id: str, body: EditRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_advisory_id(advisory_id)
    advisory = await approvals.edit_and_approve(
        runtime.store,
        runtime.bus,
        advisory_id,
        expected_version=body.version,
        body=body.body,
        actor=_actor(session),
    )
    return _json(advisory)


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
    """Flights the AI could not plan or draft for, in the current mode."""
    listed = await failures.list_failures(
        runtime.store,
        open_only=open_only,
        replay=runtime.mode is RunMode.REPLAY,
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
        await runtime.switch_mode(body.mode, case=case)  # the case is set under its lock
    else:
        await runtime.switch_mode(body.mode)
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
async def run_tick(runtime: RuntimeDep) -> Response:
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
        """A recording may be about a megabyte, a pasted notice a few dozen kilobytes."""
        if path == VOICE_PATH:
            return self.upload_bytes
        if path == NOTICE_PATH:
            return MAX_NOTICE_BODY_BYTES
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


def _log_request(scope: Scope, status: int, elapsed_s: float) -> None:
    path: str = scope.get("path", "")
    level = logging.DEBUG if path == "/healthz" else logging.INFO
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

    Extra structured fields are passed as ``extra={"json_fields": {...}}``.
    """

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
        if record.exc_info:
            entry["stack_trace"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    """Route every logger (uvicorn's included) through one JSON handler on stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


# --- app factory ------------------------------------------------------------------------


def _lifespan(
    settings: Settings, runtime_factory: RuntimeFactory
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.replays = await asyncio.to_thread(ReplayCatalogue.build, settings.data_dir)
        runtime = await runtime_factory(settings)
        app.state.runtime = runtime
        watchdog = asyncio.create_task(run_writer_watchdog(runtime), name="tephra-writer-watchdog")
        watchdog.add_done_callback(_report_task_exit)
        stop = asyncio.Event()
        scheduler: asyncio.Task[None] | None = None
        if settings.local_scheduler:
            scheduler = asyncio.create_task(
                run_local_scheduler(runtime, stop), name="tephra-local-scheduler"
            )
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


async def _startup_tick(runtime: Runtime) -> None:
    try:
        await runtime.tick(reason="startup")
    except Exception:  # a background task's error would otherwise vanish
        logger.exception("startup tick failed")


def _report_task_exit(task: asyncio.Task[None]) -> None:
    if not task.cancelled() and (exc := task.exception()) is not None:
        logger.error("%s stopped", task.get_name(), exc_info=exc)


def _include_feature_routers(app: FastAPI) -> None:
    """The feature routers import the dependencies above, so they are imported here, not at the
    top of the module (a top-level import would be circular)."""
    from tephra.api import (
        routes_ask,
        routes_backtest,
        routes_comms,
        routes_duty,
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
    ):
        app.include_router(module.router, prefix="/api")


def create_app(
    settings: Settings | None = None, *, runtime_factory: RuntimeFactory | None = None
) -> FastAPI:
    """The TEPHRA app. ``runtime_factory`` defaults to ``create_runtime`` (tests swap it)."""
    settings = settings if settings is not None else get_settings()
    app = FastAPI(
        title="TEPHRA",
        version=__version__,
        description="Volcanic-ash decision desk. Decision support only; the airline is fictional.",
        lifespan=_lifespan(settings, runtime_factory or create_runtime),
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.login_throttle = LoginThrottle()
    app.state.event_streams = StreamSlots(settings.max_event_streams)
    _install_error_handlers(app)
    # Starlette's GZip skips text/event-stream, images and woff2 by default, so the SSE stream is
    # never buffered or compressed. Added first so HttpGuard stays outermost and still sees every
    # response, including the 413 it sends itself.
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MIN_BYTES)
    app.add_middleware(HttpGuardMiddleware, upload_bytes=settings.max_upload_bytes)
    app.include_router(pages)
    app.include_router(read_api)
    app.include_router(desk_api)
    _include_feature_routers(app)
    app.include_router(tasks)
    app.mount("/static", StaticFiles(directory=WEB_DIR, check_dir=False), name="static")
    return app
