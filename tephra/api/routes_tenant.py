"""A hosted airline's own routes, ``/a/<ICAO>/api/tenant/...``: the header every airline page
draws, Go live, Feeds and push keys, and the Settings tabs (Policy, Assistant, People, Record).

Every route exists only under an airline (``require_scope``: 404 at the root). Who may call it
and in which states is ``tenancy.TENANT_ROUTES``, checked before any body here runs; a suspended
airline reads everything and changes nothing (403 ``tenant_suspended``). The request already
runs on the wall clock with the airline bound (``TenantPathMiddleware``). Every change goes
through the hosted domain (``tephra.hosted``), which records it in the airline's own chain;
these handlers add the throttles, the runtime's follow-up (start, stop, reconfigure, policy)
and the view. Errors never repeat what was typed: a model key above all.

``router`` is mounted under ``/api/tenant`` only with ``hosted`` on.
"""

import asyncio
import json
import re
from collections.abc import AsyncIterator
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from tephra.agents.budget import BudgetView
from tephra.airline import accounts
from tephra.airline.models import AirlineAnswers, DryRunResult
from tephra.api import ApiError
from tephra.api.auth import is_https, require_csrf, wall_clock_now
from tephra.api.routes_pages import WEB_DIR
from tephra.api.server import _json
from tephra.api.tenancy import TenantScope, gate, require_scope
from tephra.config import Settings
from tephra.desk import audit, connections
from tephra.hosted import golive, members, policy, tenants
from tephra.hosted.access import AccessCache
from tephra.hosted.feeds import feeds_view
from tephra.hosted.keys import KeyFormat, seal
from tephra.hosted.models import (
    AssistantBody,
    AssistantTab,
    ConfirmBody,
    FeedsView,
    GoLive,
    InviteBody,
    InviteLink,
    InviteRow,
    KeyBody,
    KeyNameBody,
    LiveBody,
    Member,
    PeopleTab,
    PolicyBody,
    PolicyTab,
    ReasonBody,
    RecordTab,
    RoleBody,
    SraBody,
    StartBody,
    TenantAssistant,
    TenantHeader,
)
from tephra.hosted.registry import TenantHandle, TenantRegistry
from tephra.hosted.settings_for import assistant_tab
from tephra.models import ConnectionView, TephraModel
from tephra.store.base import Collection, Store

__all__ = ["router"]

router = APIRouter()

Scope = Annotated[TenantScope, Depends(require_scope)]
EXPORT_LIMIT: Final = 20_000
EXPORT_PAGE: Final = 500
_MEMBER_ID: Final = re.compile(r"MB-[0-9a-f]{10}")
_INVITE_ID: Final = re.compile(r"IV-[0-9a-f]{10}")
_CONNECTION_ID: Final = re.compile(r"CN-[0-9a-f]{10}")


class KeyList(TephraModel):
    keys: list[ConnectionView]


# --- helpers ----------------------------------------------------------------------------


def _registry(request: Request) -> TenantRegistry:
    registry: TenantRegistry = request.app.state.registry
    return registry


def _root(request: Request) -> Store:
    store: Store = request.app.state.runtime.store
    return store


def _site(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _access(request: Request) -> AccessCache:
    access: AccessCache = request.app.state.access
    return access


def _member(scope: TenantScope) -> Member:
    assert scope.member is not None, "an airline route is called by a member"
    return scope.member


def _by(scope: TenantScope) -> str:
    return tenants.member_by(_member(scope))


def _is_ops_manager(scope: TenantScope) -> bool:
    return scope.role == "ops_manager"


async def _fresh(request: Request, scope: TenantScope) -> TenantHandle:
    """The handle with the record as stored now (after a change)."""
    handle = await _registry(request).reload(scope.icao)
    if handle is None:
        raise ApiError(404, "no_such_airline", "No such airline")
    return handle


async def _answers(request: Request, handle: TenantHandle) -> AirlineAnswers:
    record = await accounts.get_record(_root(request), handle.record.airline_id)
    return record.submitted()


async def count_write(request: Request, scope: Scope) -> None:
    """Every change is store writes: an airline makes at most 200 a day (``hosted_writes``)."""
    gate(request, "hosted_writes", scope.icao, "too_many_requests", "Too many changes today")


Write = [Depends(require_csrf), Depends(count_write)]


# --- the header and Go live -------------------------------------------------------------


async def _header(request: Request, scope: TenantScope, handle: TenantHandle) -> Response:
    return _json(await _registry(request).header(handle, _member(scope)))


@router.get("/header", response_model=TenantHeader)
async def get_header(request: Request, scope: Scope) -> Response:
    return await _header(request, scope, scope.handle)


async def _golive(request: Request, handle: TenantHandle) -> GoLive:
    return await _registry(request).go_live(handle)


@router.get("/golive", response_model=GoLive)
async def get_golive(request: Request, scope: Scope) -> Response:
    return _json(await _golive(request, scope.handle))


_BLOCKED: Final = {
    "checklist": (409, "checklist_open", "Finish the checklist first"),
    "region": (409, "region", "Choose a region first"),
    "airline_limit_reached": (
        409,
        "airline_limit_reached",
        "All airline places on this site are in use",
    ),
    "site_memory": (409, "site_memory", "The site's memory is full: no airline starts now"),
}


@router.post("/start", response_model=TenantHeader, dependencies=Write)
async def start(body: StartBody, request: Request, scope: Scope) -> Response:
    """setup → shadow: the checklist done, a region, a free place and memory to spare."""
    handle = scope.handle
    checked = await _golive(request, handle)
    if checked.blocked is not None:
        status, code, detail = _BLOCKED[checked.blocked]
        raise ApiError(status, code, detail)
    answers = await _answers(request, handle)
    region = golive.start_region(answers, _registry(request).demo.airports, body.region)
    _registry(request).require_memory()
    await tenants.start(
        _root(request),
        scope.icao,
        region=region,
        by=_by(scope),
        max_slots=_site(request).hosted_max_tenants,
        space=handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).start(scope.icao)
    return await _header(request, scope, await _fresh(request, scope))


@router.post("/live", response_model=TenantHeader, dependencies=Write)
async def go_live(body: LiveBody, request: Request, scope: Scope) -> Response:
    """shadow → live, with the airline's code typed and the ops manager's attestation."""
    if body.confirm_icao.strip().upper() != scope.icao:
        raise ApiError(
            422,
            "confirm_icao",
            f"Type {scope.icao} to confirm",
            problems=["confirm_icao: not this airline's code"],
        )
    await tenants.go_live(
        _root(request), scope.icao, by=_by(scope), space=scope.handle.space, at=wall_clock_now()
    )
    await _registry(request).reconfigure(scope.icao)
    return await _header(request, scope, await _fresh(request, scope))


@router.post("/shadow", response_model=TenantHeader, dependencies=Write)
async def back_to_shadow(body: ReasonBody, request: Request, scope: Scope) -> Response:
    await tenants.back_to_shadow(
        _root(request),
        scope.icao,
        by=_by(scope),
        reason=body.reason,
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).reconfigure(scope.icao)
    return await _header(request, scope, await _fresh(request, scope))


@router.post("/stop", response_model=TenantHeader, dependencies=Write)
async def stop_runs(body: ReasonBody, request: Request, scope: Scope) -> Response:
    """shadow or live → setup: the runtime stops and the place is freed (D27)."""
    await tenants.stop_runs(
        _root(request),
        scope.icao,
        by=_by(scope),
        reason=body.reason,
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).stop(scope.icao, reason="stopped by the airline")
    return await _header(request, scope, await _fresh(request, scope))


# --- Feeds and push keys ----------------------------------------------------------------


@router.get("/feeds", response_model=FeedsView)
async def get_feeds(request: Request, scope: Scope) -> Response:
    """The three feed cards, and the push keys for ops managers (hints only)."""
    handle = scope.handle
    keys = await _registry(request).connections(scope.icao) if _is_ops_manager(scope) else []
    view = feeds_view(
        icao=scope.icao,
        state=handle.record.state,
        answers=await _answers(request, handle),
        stats=handle.space.feed_stats,
        conn_stats=handle.space.conn_stats,
        connections=keys,
        now=wall_clock_now(),
        show_keys=_is_ops_manager(scope),
    )
    return _json(view)


async def _json_body(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except (ValueError, RecursionError):
        raise ApiError(422, "not_a_push", "file: not JSON") from None


@router.post(
    "/feeds/dry-run",
    response_model=DryRunResult,
    dependencies=[Depends(require_csrf)],
)
async def dry_run(request: Request, scope: Scope) -> Response:
    """A file checked as a push would be, against the wall clock now: nothing is taken in,
    and it counts on the Feeds cards as a check with no key."""
    gate(
        request,
        "airline_dry_runs",
        f"hosted:{scope.icao}",
        "too_many_requests",
        "Too many dry runs this hour",
    )
    raw = await _json_body(request)
    if not isinstance(raw, dict):
        raise ApiError(422, "not_a_push", "file: Input should be an object")
    at = wall_clock_now()
    try:
        result = connections.dry_run(raw, at)
    except connections.NotAPush as exc:
        raise ApiError(422, "not_a_push", str(exc)) from None
    scope.handle.space.feed_stats.record_dry_run(result, wall_at=at, connection_id=None)
    return _json(result)


UPLOADER: Final = WEB_DIR / "kit" / "push.py"
"""The uploader (standard library only) the Feeds page offers as "Download uploader": the same file
for every airline, nothing of the airline or the site written into it. ``/static/kit/`` answers
404 with ``hosted`` on, so this member-only route is its one way out."""


@router.get("/feeds/uploader")
async def get_uploader(scope: Scope) -> Response:
    """push.py as a file to save (``Content-Disposition: attachment``), for any of the airline's
    people in any state; it reads nothing from the store."""
    body = await asyncio.to_thread(UPLOADER.read_bytes)
    return Response(
        body,
        media_type="text/x-python; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="push.py"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/keys", response_model=KeyList)
async def get_keys(request: Request, scope: Scope) -> Response:
    stats = scope.handle.space.conn_stats
    found = await _registry(request).connections(scope.icao)
    return _json(KeyList(keys=[connections.view(stats.merged(c)) for c in found]))


@router.post("/keys", response_model=ConnectionView, dependencies=Write)
async def create_key(body: KeyNameBody, request: Request, scope: Scope) -> Response:
    """A push key; the answer carries it, the only time it is shown."""
    made, key = await _registry(request).create_key(scope.icao, body.name, by=_by(scope))
    return _json(connections.view(made, key))


def _checked(value: str, pattern: re.Pattern[str], what: str) -> str:
    """A path id of the expected shape, else the same 404 as one that does not exist."""
    if pattern.fullmatch(value) is None:
        raise ApiError(404, "not_found", f"No such {what}")
    return value


@router.post("/keys/{connection_id}/rotate", response_model=ConnectionView, dependencies=Write)
async def rotate_key(connection_id: str, request: Request, scope: Scope) -> Response:
    """A new key in place of the old one, which stops at once (no grace window)."""
    try:
        made, key = await _registry(request).rotate_key(
            scope.icao, _checked(connection_id, _CONNECTION_ID, "key"), by=_by(scope)
        )
    except connections.ConnectionNotFound:
        raise ApiError(404, "not_found", "No such key") from None
    return _json(connections.view(made, key))


@router.post("/keys/{connection_id}/revoke", response_model=ConnectionView, dependencies=Write)
async def revoke_key(connection_id: str, request: Request, scope: Scope) -> Response:
    try:
        gone = await _registry(request).revoke_key(
            scope.icao, _checked(connection_id, _CONNECTION_ID, "key"), by=_by(scope)
        )
    except connections.ConnectionNotFound:
        raise ApiError(404, "not_found", "No such key") from None
    return _json(connections.view(gone))


# --- Settings: Policy ------------------------------------------------------------------


async def _policy_tab(request: Request, handle: TenantHandle) -> PolicyTab:
    with handle.space.bound():
        versions = await policy.list_versions(handle.space.store)
    return policy.policy_tab(_registry(request).demo.policy, versions, handle.record)


@router.get("/policy", response_model=PolicyTab)
async def get_policy(request: Request, scope: Scope) -> Response:
    return _json(await _policy_tab(request, scope.handle))


@router.post("/policy", response_model=PolicyTab, dependencies=Write)
async def change_policy(body: PolicyBody, request: Request, scope: Scope) -> Response:
    """Version n+1 from the version the editor saw; the runtime runs on it from its next step."""
    await tenants.set_policy_version(
        _root(request),
        scope.icao,
        body.changes,
        base_version=body.base_version,
        note=body.note,
        base_policy=_registry(request).demo.policy,
        by=_by(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).apply_policy(scope.icao)
    return _json(await _policy_tab(request, await _fresh(request, scope)))


@router.post("/policy/confirm", response_model=PolicyTab, dependencies=Write)
async def confirm_policy(body: ConfirmBody, request: Request, scope: Scope) -> Response:
    await tenants.confirm_policy(
        _root(request),
        scope.icao,
        version=body.version,
        by=_by(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    return _json(await _policy_tab(request, await _fresh(request, scope)))


@router.post("/policy/sra", response_model=PolicyTab, dependencies=Write)
async def record_sra(body: SraBody, request: Request, scope: Scope) -> Response:
    """The airline records its SRA acceptance of the current version (TEPHRA does not check
    it); the policy's label changes from ILLUSTRATIVE to the acceptance."""
    await tenants.record_sra(
        _root(request),
        scope.icao,
        version=body.version,
        accepted_by=body.accepted_by,
        accepted_on=body.accepted_on,
        sra_ref=body.sra_ref,
        by=_by(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).apply_policy(scope.icao)
    return _json(await _policy_tab(request, await _fresh(request, scope)))


@router.post("/policy/sra/withdraw", response_model=PolicyTab, dependencies=Write)
async def withdraw_sra(body: ReasonBody, request: Request, scope: Scope) -> Response:
    await tenants.withdraw_sra(
        _root(request),
        scope.icao,
        reason=body.reason,
        by=_by(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).apply_policy(scope.icao)
    return _json(await _policy_tab(request, await _fresh(request, scope)))


# --- Settings: Assistant ---------------------------------------------------------------


async def _assistant_tab(request: Request, handle: TenantHandle) -> AssistantTab:
    runtime = handle.runtime
    budget: BudgetView | None = None
    if runtime is not None:
        with handle.space.bound():
            budget = await runtime.budget_view()
    return assistant_tab(handle.record, _site(request), budget=budget)


@router.get("/assistant", response_model=AssistantTab)
async def get_assistant(request: Request, scope: Scope) -> Response:
    return _json(await _assistant_tab(request, scope.handle))


@router.put("/assistant", response_model=AssistantTab, dependencies=Write)
async def put_assistant(body: AssistantBody, request: Request, scope: Scope) -> Response:
    """The models (TEPHRA's free-tier table only), each one's daily limit on the airline's
    key, and the share held for the Desk; the runtime takes them without a restart."""
    assistant = TenantAssistant(
        model=body.model,
        model_lite=body.model_lite,
        reserve_share=body.reserve_share,
        daily_limits=body.daily_limits,
    )
    await tenants.set_assistant(
        _root(request),
        scope.icao,
        assistant,
        by=_by(scope),
        settings=_site(request),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).reconfigure(scope.icao)
    return _json(await _assistant_tab(request, await _fresh(request, scope)))


@router.put("/assistant/key", response_model=AssistantTab, dependencies=Write)
async def put_key(body: KeyBody, request: Request, scope: Scope) -> Response:
    """The airline's Google AI Studio key, sealed at once and never shown again (only its
    last four). A malformed key is refused without a word of it."""
    gate(request, "hosted_key_sets", scope.icao, "too_many_requests", "Ten key changes a day")
    at = wall_clock_now()
    try:
        sealed = seal(scope.icao, body.key, _site(request), by=_by(scope), at=at)
    except KeyFormat:
        raise ApiError(
            422,
            "key_format",
            "That is not a Google AI Studio key",
            problems=["key: letters, digits, - and _ only, 30 to 100 of them"],
        ) from None
    await tenants.set_key(
        _root(request), scope.icao, sealed, by=_by(scope), space=scope.handle.space, at=at
    )
    await _registry(request).reconfigure(scope.icao)
    return _json(await _assistant_tab(request, await _fresh(request, scope)))


@router.delete("/assistant/key", response_model=AssistantTab, dependencies=Write)
async def delete_key(request: Request, scope: Scope) -> Response:
    """Every model step then says AI UNAVAILABLE: no model key is set (nothing stands in)."""
    await tenants.set_key(
        _root(request),
        scope.icao,
        None,
        by=_by(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    await _registry(request).reconfigure(scope.icao)
    return _json(await _assistant_tab(request, await _fresh(request, scope)))


# --- Settings: People ------------------------------------------------------------------


async def _people(request: Request, scope: TenantScope, handle: TenantHandle) -> Response:
    tab = await members.people_tab(
        _root(request), handle.record, _member(scope), at=wall_clock_now()
    )
    return _json(tab)


@router.get("/people", response_model=PeopleTab)
async def get_people(request: Request, scope: Scope) -> Response:
    return await _people(request, scope, scope.handle)


def _origin(request: Request) -> str:
    scheme = "https" if is_https(request) else request.url.scheme
    return f"{scheme}://{request.headers.get('host', request.url.netloc)}"


@router.post("/people/invites", response_model=InviteLink, dependencies=Write)
async def invite(body: InviteBody, request: Request, scope: Scope) -> Response:
    """A one-time link for one email and role, shown once: TEPHRA sends no email."""
    gate(request, "hosted_invites", scope.icao, "too_many_requests", "Twenty invites a day")
    made, token = await members.invite(
        _root(request),
        scope.icao,
        body.email,
        body.role,
        by=_member(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    row = InviteRow(
        id=made.id,
        email=made.email,
        role=made.role,
        created=made.created,
        expires_at=made.expires_at,
    )
    return _json(InviteLink(invite=row, link=f"{_origin(request)}/join#{token}"))


@router.post("/people/invites/{invite_id}/revoke", response_model=PeopleTab, dependencies=Write)
async def revoke_invite(invite_id: str, request: Request, scope: Scope) -> Response:
    await members.revoke_invite(
        _root(request),
        scope.icao,
        _checked(invite_id, _INVITE_ID, "invite"),
        by=_member(scope),
        space=scope.handle.space,
        at=wall_clock_now(),
    )
    return await _people(request, scope, scope.handle)


@router.post("/people/me/leave", status_code=204, dependencies=[Depends(require_csrf)])
async def leave(request: Request, scope: Scope) -> Response:
    """Leave the airline (also while it is suspended); the last ops manager cannot."""
    await members.leave(
        _root(request),
        scope.icao,
        _member(scope).id,
        space=scope.handle.space,
        access=_access(request),
        at=wall_clock_now(),
    )
    await _fresh(request, scope)
    return Response(status_code=204)


@router.post("/people/{member_id}/role", response_model=PeopleTab, dependencies=Write)
async def set_role(member_id: str, body: RoleBody, request: Request, scope: Scope) -> Response:
    await members.set_role(
        _root(request),
        scope.icao,
        _checked(member_id, _MEMBER_ID, "member"),
        body.role,
        by=_member(scope),
        space=scope.handle.space,
        access=_access(request),
        at=wall_clock_now(),
    )
    return await _people(request, scope, await _fresh(request, scope))


@router.post("/people/{member_id}/remove", response_model=PeopleTab, dependencies=Write)
async def remove(member_id: str, request: Request, scope: Scope) -> Response:
    await members.remove(
        _root(request),
        scope.icao,
        _checked(member_id, _MEMBER_ID, "member"),
        by=_member(scope),
        space=scope.handle.space,
        access=_access(request),
        at=wall_clock_now(),
    )
    return await _people(request, scope, await _fresh(request, scope))


# --- Settings: Record ------------------------------------------------------------------


def _left(request: Request, name: str, icao: str) -> bool:
    return not getattr(request.app.state, name).blocked(icao)


async def _record_tab(
    request: Request, scope: TenantScope, handle: TenantHandle, before_seq: int | None
) -> RecordTab:
    return await _registry(request).record_view(
        handle,
        before_seq=before_seq,
        is_ops_manager=_is_ops_manager(scope),
        can_check=_left(request, "hosted_chain_checks", scope.icao),
        can_export=_left(request, "hosted_exports", scope.icao),
    )


@router.get("/record", response_model=RecordTab)
async def get_record(
    request: Request,
    scope: Scope,
    before_seq: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    """Fifty entries newest first (``Store.page``) and the head TEPHRA holds: never a walk."""
    return _json(await _record_tab(request, scope, scope.handle, before_seq))


def _refuse_over_allowance(request: Request, scope: TenantScope) -> None:
    """A whole walk or an export reads every entry: refused when that would pass the
    airline's daily allowance."""
    head = audit.chain(scope.handle.space.store).head
    entries = 0 if head is None else head.entries
    if request.app.state.meter.would_exceed(scope.icao, _site(request), entries):
        raise ApiError(
            503,
            "airline_paused",
            "Reading the whole record now would pass this airline's free daily allowance",
        )


@router.post("/record/check", response_model=RecordTab, dependencies=[Depends(require_csrf)])
async def check_record(request: Request, scope: Scope) -> Response:
    """The whole chain walked from its first entry (once a day), recorded as CHAIN_CHECKED;
    refused when its reads would pass the airline's free daily allowance."""
    _refuse_over_allowance(request, scope)
    gate(request, "hosted_chain_checks", scope.icao, "too_many_requests", "Once a day")
    await _registry(request).check_record(scope.handle, by=_by(scope))
    return _json(await _record_tab(request, scope, await _fresh(request, scope), None))


@router.get("/record/export")
async def export_record(request: Request, scope: Scope) -> StreamingResponse:
    """Every entry oldest first as NDJSON (at most 20,000, read 500 at a time), once a day."""
    _refuse_over_allowance(request, scope)
    gate(request, "hosted_exports", scope.icao, "too_many_requests", "Once a day")
    store = scope.handle.space.store
    filename = f"{scope.icao}-record-{wall_clock_now():%Y%m%d}.ndjson"
    return StreamingResponse(
        _ndjson(store),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _ndjson(store: Store) -> AsyncIterator[bytes]:
    cursor, sent = 0, 0
    while sent < EXPORT_LIMIT:
        docs = await store.page(
            Collection.AUDIT,
            field="seq",
            before=cursor,
            limit=min(EXPORT_PAGE, EXPORT_LIMIT - sent),
            descending=False,
        )
        if not docs:
            return
        yield b"".join(_line(doc) for doc in docs)
        sent += len(docs)
        cursor = int(docs[-1]["seq"])
        if len(docs) < EXPORT_PAGE:
            return


def _line(doc: BaseModel | dict[str, Any]) -> bytes:
    data = doc.model_dump(mode="json") if isinstance(doc, BaseModel) else doc
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode() + b"\n"
