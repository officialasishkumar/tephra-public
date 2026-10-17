"""Airline onboarding accounts, the private workspace's API, the Desk's airline review and the
own-fleet read (``GET /api/fleet``). The account comes first: its onboarding pages are a draft
saved on each Next and Back (``PUT /api/airline/draft``) until Review submits them
(``POST /api/airline/submit``); the Desk never sees a draft.

``router`` is mounted under ``/api`` by the app factory. Every ``/api/airline/*`` and
``/api/desk/airlines*`` route answers 404 ``feature_off`` unless ``onboard`` is in
``TEPHRA_FEATURES``; ``/api/airline/*`` (but ``session``) answers 503 ``accounts_off`` without
a session secret. Nothing here publishes an event, writes the audit trail or changes the
picture: an airline's record is private to it and this site's dispatchers, and a dry run takes
nothing in. Errors never repeat input (no email, no password).
"""

import asyncio
import json
import logging
import re
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError

from tephra.airline import accounts, passwords
from tephra.airline.models import (
    AccountCreate,
    AccountCreated,
    AirlineAnswers,
    AirlineDeskRow,
    AirlineDeskView,
    AirlineList,
    AirlineLogin,
    AirlineRecord,
    AirlineSessionView,
    AirlineView,
    AnswersUpdate,
    AssistantUpdate,
    DeclineAirline,
    DeleteAccount,
    DeleteAirline,
    DeskStatus,
    DraftUpdate,
    DryRunResult,
    Recover,
    RecoveryCode,
    SignIn,
    Submit,
    VerifyAirline,
)
from tephra.airline.policy_check import EDITABLE, PolicyRefused, apply_changes
from tephra.airline.sessions import (
    AirlineClaims,
    AirlineContext,
    LoginContext,
    accounts_enabled,
    claims_of,
    clear_airline_cookie,
    client_key_64,
    member_claims,
    read_claims,
    require_accounts,
    require_airline,
    require_login,
    require_onboard,
    set_airline_cookie,
    sign_out_everywhere,
)
from tephra.api import ApiError
from tephra.api.auth import VISITOR_ROLE_DETAIL, LoginThrottle, require_csrf, wall_clock_now
from tephra.api.server import DeskSession, RuntimeDep, SettingsDep, _actor, _json
from tephra.desk import connections
from tephra.feeds.routes import ROUTES_FILE
from tephra.models import ErrorBody, FleetResponse, SessionInfo, TephraModel, is_airline_callsign
from tephra.pipeline import Runtime

__all__ = ["router"]

logger = logging.getLogger(__name__)

router = APIRouter()

SITE: Final = "site"
PURGE_EVERY_S: Final = 3600.0
TRIES_HEADER: Final = "X-Tephra-Tries-Left"
_AIRLINE_ID: Final = re.compile(r"AL-[0-9a-f]{12}")

Airline = Annotated[AirlineContext, Depends(require_airline)]
SignedIn = Annotated[LoginContext, Depends(require_login)]
DELETE_REFUSALS: Final = {
    "hosted_airline": "Your airline is hosted on TEPHRA. TEPHRA's operators delete its data.",
    "last_ops_manager": "You are the last ops manager of an airline on TEPHRA. Make someone "
    "else ops manager first.",
}
Accounts = [Depends(require_csrf), Depends(require_accounts)]


class PendingSummary(TephraModel):
    pending: int


# --- helpers ----------------------------------------------------------------------------


def _throttle(request: Request, name: str) -> LoginThrottle:
    throttle: LoginThrottle = getattr(request.app.state, name)
    return throttle


def _refuse_if_blocked(
    request: Request, checks: Sequence[tuple[str, str]], error: str, detail: str
) -> None:
    """429 with ``Retry-After`` (the longest wait) when any ``(throttle, key)`` is blocked."""
    waits = [
        _throttle(request, name).retry_after_s(key)
        for name, key in checks
        if _throttle(request, name).blocked(key)
    ]
    if waits:
        raise ApiError(429, error, detail, headers={"Retry-After": str(max(waits))})


def _problems(exc: ValidationError) -> list[str]:
    """The app's 422 shape: dotted location, colon, message; never the input."""
    return [
        f"{'.'.join(str(part) for part in error.get('loc', ()))}: {error.get('msg', 'invalid')}"
        for error in exc.errors()
    ]


def _invalid(problems: list[str]) -> ApiError:
    return ApiError(422, "validation_failed", "Request is invalid", problems=problems)


def _check_policy(answers: AirlineAnswers, runtime: Runtime) -> None:
    """The ash-policy changes name values this policy lets an airline change, and the policy
    with them applied still passes the policy file's own rules."""
    changes = answers.policy.changes
    unknown = [
        f"answers.policy.changes.{index}.name: not a value an airline can change"
        for index, change in enumerate(changes)
        if change.name not in EDITABLE
    ]
    if unknown:
        raise _invalid(unknown)
    try:
        apply_changes(runtime.policy, changes)
    except PolicyRefused as exc:
        raise _invalid([f"answers.policy.changes: {exc}"]) from None


async def _designators(request: Request, runtime: Runtime) -> frozenset[str]:
    """The 3-letter prefixes of the airline callsigns in TEPHRA's route table (read once)."""
    held: frozenset[str] | None = getattr(request.app.state, "airline_designators", None)
    if held is None:
        path = runtime.settings.data_dir / ROUTES_FILE
        routes = json.loads(await asyncio.to_thread(path.read_bytes))["routes"]
        held = frozenset(sign[:3] for sign in routes if is_airline_callsign(sign))
        request.app.state.airline_designators = held
    return held


async def _flags(
    request: Request, runtime: Runtime, answers: AirlineAnswers, email: str
) -> list[str]:
    return accounts.reviewer_flags(
        answers,
        email,
        airports=runtime.airports.icaos(),
        designators=await _designators(request, runtime),
    )


def _bad_credentials(detail: str, tries_left: int | None = None) -> ApiError:
    headers = {} if tries_left is None else {TRIES_HEADER: str(tries_left)}
    return ApiError(401, "bad_credentials", detail, headers=headers)


def _version_conflict() -> ApiError:
    return ApiError(409, "version_conflict", "This airline changed since you loaded it")


def _record_failure(request: Request, client: str, key: str, email_throttle: str) -> int:
    """One failed try on the client's and the email's throttles; the smaller tries left."""
    _throttle(request, "airline_login").record_failure(client)
    _throttle(request, email_throttle).record_failure(key)
    return min(
        _throttle(request, "airline_login").remaining(client),
        _throttle(request, email_throttle).remaining(key),
    )


def _count_write(request: Request, airline_id: str) -> None:
    """Every save is a store write: one airline's saves, and all airlines' together, are
    bounded so they cannot use up the store's daily free writes for the whole site."""
    _refuse_if_blocked(
        request,
        [("airline_writes", airline_id), ("airline_writes_all", SITE)],
        "too_many_requests",
        "Too many saves today",
    )
    _throttle(request, "airline_writes").record_failure(airline_id)
    _throttle(request, "airline_writes_all").record_failure(SITE)


async def _purge_now_and_then(request: Request, runtime: Any) -> None:
    """Stale drafts go (accounts.purge_stale_drafts) at most once per PURGE_EVERY_S in this
    process, on the way to a new account: reading every draft is not for every request."""
    now = wall_clock_now()
    last: datetime | None = getattr(request.app.state, "airline_purged_at", None)
    if last is not None and (now - last).total_seconds() < PURGE_EVERY_S:
        return
    request.app.state.airline_purged_at = now
    await accounts.purge_stale_drafts(runtime.store, now=now)


def _view(
    model: BaseModel, request: Request, record: AirlineRecord | None, login: AirlineLogin
) -> Response:
    """``record`` None: a member-only login (it joined a hosted airline by invite)."""
    response = _json(model)
    set_airline_cookie(response, request, _claims(record, login))
    return response


def _claims(record: AirlineRecord | None, login: AirlineLogin) -> AirlineClaims:
    return member_claims(login) if record is None else claims_of(record, login)


def _hosted(request: Request) -> bool:
    return "hosted" in request.app.state.settings.features


async def _json_body(request: Request) -> Any:
    try:
        return json.loads(await request.body())
    except (ValueError, RecursionError):
        raise _invalid(["body: not JSON"]) from None


# --- the account ------------------------------------------------------------------------


@router.get("/airline/session", response_model=AirlineSessionView)
async def get_session(request: Request, settings: SettingsDep) -> Response:
    """From the cookie alone: no store read, so the nav of every page costs nothing."""
    claims = read_claims(request)
    return _json(
        AirlineSessionView(
            accounts=accounts_enabled(settings),
            signed_in=claims is not None,
            icao=None if claims is None else claims.icao or None,
            name=None if claims is None else claims.name or None,
        )
    )


@router.post(
    "/airline/accounts",
    status_code=201,
    response_model=AccountCreated,
    responses={409: {"model": ErrorBody}, 429: {"model": ErrorBody}, 503: {"model": ErrorBody}},
    dependencies=Accounts,
)
async def create_account(request: Request, runtime: RuntimeDep) -> Response:
    """The account first, its onboarding a draft. Cheapest first: the attempt throttle, the
    body, the accepted-signup throttles, the caps, then the hash and the two writes. The body
    is read here, not by FastAPI, so a flood of invalid bodies meets the throttle before any
    validation."""
    client = client_key_64(request)
    _refuse_if_blocked(
        request,
        [("airline_signup_attempts", client)],
        "too_many_requests",
        "Too many tries from this address",
    )
    _throttle(request, "airline_signup_attempts").record_failure(client)
    try:
        body = AccountCreate.model_validate(await _json_body(request))
    except ValidationError as exc:
        raise _invalid(_problems(exc)) from None
    _refuse_if_blocked(
        request,
        [("airline_signups", client), ("airline_signups_all", SITE)],
        "too_many_requests",
        "Too many new airlines from this address or on this server today",
    )
    await _purge_now_and_then(request, runtime)
    if await accounts.onboarding_full(runtime.store):
        raise ApiError(503, "onboarding_full", "New airlines are paused on this server")
    password_hash = await passwords.hashed(body.password)
    code = passwords.new_recovery_code()
    try:
        record, login = await accounts.create_account(
            runtime.store,
            email=body.email,
            password_hash=password_hash,
            recovery_sha256=passwords.code_sha256(code),
            at=wall_clock_now(),
        )
    except accounts.EmailTaken:
        # counted like an account made: asking whether an email has an account costs this
        # address one of its sign-ups a day (not the site's, which a prober would use up)
        _throttle(request, "airline_signups").record_failure(client)
        raise ApiError(
            409, "email_taken", "An account with this email exists. Sign in instead."
        ) from None
    _throttle(request, "airline_signups").record_failure(client)
    _throttle(request, "airline_signups_all").record_failure(SITE)
    response = _view(
        AccountCreated(airline=AirlineView.of(record), recovery_code=code), request, record, login
    )
    response.status_code = 201
    return response


@router.post("/airline/sign-in", response_model=AirlineSessionView, dependencies=Accounts)
async def sign_in(body: SignIn, request: Request, runtime: RuntimeDep) -> Response:
    """An unknown email costs one scrypt and counts on both throttles like a wrong password,
    so neither the answer, the tries left nor the 429 tells whether it has an account. A
    success clears only that email's count: the address's failures age out, so signing in to
    one's own account never resets guessing at other emails."""
    client, key = client_key_64(request), accounts.login_key(body.email)
    _refuse_if_blocked(
        request,
        [("airline_login", client), ("airline_login_email", key)],
        "too_many_attempts",
        "Too many tries; sign-in waits",
    )
    login = await accounts.get_login(runtime.store, key)
    matched = await passwords.check_password(
        body.password, None if login is None else login.password
    )
    if login is None or not matched:
        left = _record_failure(request, client, key, "airline_login_email")
        raise _bad_credentials("That email and password don't match", left)
    _throttle(request, "airline_login_email").clear(key)
    record = await _record_or_none(runtime, login)
    claims = _claims(record, login)
    if _hosted(request):
        await accounts.note_sign_in(runtime.store, key, at=wall_clock_now())
    view = AirlineSessionView(
        accounts=True,
        signed_in=True,
        icao=claims.icao or None,
        name=claims.name or None,
        status=None if record is None else record.status,
    )
    return _view(view, request, record, login)


@router.post("/airline/recover", response_model=RecoveryCode, dependencies=Accounts)
async def recover(body: Recover, request: Request, runtime: RuntimeDep) -> Response:
    """A matching recovery code sets the new password and a new code, and signs every other
    browser out. Its throttle is apart from the password's, so password guesses against an
    email never lock its owner out of recovery."""
    client, key = client_key_64(request), accounts.login_key(body.email)
    _refuse_if_blocked(
        request,
        [("airline_login", client), ("airline_recover_email", key)],
        "too_many_attempts",
        "Too many tries; recovery waits",
    )
    login = await accounts.get_login(runtime.store, key)
    stored = None if login is None else login.recovery_sha256
    if stored is None or not passwords.codes_match(body.recovery_code, stored):
        left = _record_failure(request, client, key, "airline_recover_email")
        raise _bad_credentials("That email and recovery code don't match", left)
    code = passwords.new_recovery_code()
    try:
        login = await accounts.set_password(
            runtime.store,
            key,
            password_hash=await passwords.hashed(body.new_password),
            recovery_sha256=passwords.code_sha256(code),
            expected_recovery_sha256=stored,
            at=wall_clock_now(),
        )
    except (accounts.AirlineNotFound, accounts.VersionConflict):
        raise _bad_credentials("That email and recovery code don't match") from None
    _throttle(request, "airline_recover_email").clear(key)
    _throttle(request, "airline_login_email").clear(key)
    if _hosted(request):
        request.app.state.access.drop(login_key=key)
    record = await _record_or_none(runtime, login)
    return _view(RecoveryCode(recovery_code=code), request, record, login)


async def _record_or_none(runtime: Runtime, login: AirlineLogin) -> AirlineRecord | None:
    """The login's onboarding record; None for a member-only login."""
    if login.airline_id is None:
        return None
    try:
        return await accounts.get_record(runtime.store, login.airline_id)
    except accounts.AirlineNotFound:
        raise ApiError(401, "unauthenticated", "Sign in to your airline workspace") from None


@router.post("/airline/sign-out", status_code=204, dependencies=Accounts)
async def sign_out(request: Request, runtime: RuntimeDep) -> Response:
    """Ends the session on the server too: a copy of the cookie stops working at once. With
    hosted airlines, signing out signs out every device (an airline's pages are private)."""
    claims = read_claims(request)
    if claims is not None and _hosted(request):
        await sign_out_everywhere(runtime.store, claims.login_key, access=request.app.state.access)
    elif claims is not None:
        await accounts.end_sessions(runtime.store, claims.login_key, version=claims.version)
    response = Response(status_code=204)
    clear_airline_cookie(response, request)
    return response


@router.get("/airline/me", response_model=AirlineView)
async def get_me(airline: Airline) -> Response:
    return _json(AirlineView.of(airline.record))


@router.put("/airline/draft", response_model=AirlineView, dependencies=[Depends(require_csrf)])
async def put_draft(
    body: DraftUpdate, request: Request, airline: Airline, runtime: RuntimeDep
) -> Response:
    """A page's Next or Back while the airline has not submitted: the pages as typed."""
    _count_write(request, airline.record.id)
    try:
        record = await accounts.save_draft(
            runtime.store,
            airline.record.id,
            version=body.version,
            draft=body.draft,
            at=wall_clock_now(),
        )
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.AlreadySubmitted as exc:
        raise _already_submitted(exc.status) from None
    return _json(AirlineView.of(record))


@router.post("/airline/submit", response_model=AirlineView, dependencies=[Depends(require_csrf)])
async def submit(body: Submit, request: Request, airline: Airline, runtime: RuntimeDep) -> Response:
    """Review's Submit for verification: the answers checked as a whole, then pending. The
    cookie is signed again with the airline's ICAO and name."""
    _count_write(request, airline.record.id)
    _check_policy(body.answers, runtime)
    if await accounts.submissions_full(runtime.store):
        raise ApiError(503, "onboarding_full", "New airlines are paused on this server")
    try:
        record = await accounts.submit(
            runtime.store,
            airline.record.id,
            version=body.version,
            answers=body.answers,
            flags=await _flags(request, runtime, body.answers, airline.record.email),
            at=wall_clock_now(),
        )
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.AlreadySubmitted as exc:
        raise _already_submitted(exc.status) from None
    return _view(AirlineView.of(record), request, record, airline.login)


def _already_submitted(status: str) -> ApiError:
    return ApiError(409, "already_submitted", f"This airline was submitted and is {status}")


def _locked(status: str) -> ApiError:
    if status == "draft":
        return ApiError(403, "answers_locked", "Submit your onboarding first.")
    return ApiError(
        403,
        "answers_locked",
        f"Your answers are kept as {status}. Ask a TEPHRA dispatcher to change them.",
    )


@router.put("/airline/answers", response_model=AirlineView, dependencies=[Depends(require_csrf)])
async def put_answers(
    body: AnswersUpdate, request: Request, airline: Airline, runtime: RuntimeDep
) -> Response:
    """Editable while pending; the cookie is signed again when the name or ICAO changed."""
    _count_write(request, airline.record.id)
    _check_policy(body.answers, runtime)
    try:
        record = await accounts.update_answers(
            runtime.store,
            airline.record.id,
            version=body.version,
            answers=body.answers,
            flags=await _flags(request, runtime, body.answers, airline.record.email),
            at=wall_clock_now(),
        )
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.AnswersLocked as exc:
        raise _locked(exc.status) from None
    claims = claims_of(record, airline.login)
    if (claims.icao, claims.name) == (airline.claims.icao, airline.claims.name):
        return _json(AirlineView.of(record))
    return _view(AirlineView.of(record), request, record, airline.login)


@router.put("/airline/assistant", response_model=AirlineView, dependencies=[Depends(require_csrf)])
async def put_assistant(
    body: AssistantUpdate, request: Request, airline: Airline, runtime: RuntimeDep
) -> Response:
    """Allowed once submitted, in every status: only the provider and the model names are
    stored."""
    _count_write(request, airline.record.id)
    try:
        record = await accounts.update_assistant(
            runtime.store,
            airline.record.id,
            version=body.version,
            assistant=body.assistant,
            at=wall_clock_now(),
        )
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.AnswersLocked as exc:
        raise _locked(exc.status) from None
    return _json(AirlineView.of(record))


@router.post("/airline/delete", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_account(
    body: DeleteAccount, request: Request, signed_in: SignedIn, runtime: RuntimeDep
) -> Response:
    """The password again (throttled as sign-in), then the login and its record go. With
    hosted airlines, an airline that is hosted keeps its account (409 ``hosted_airline``) and
    the last ops manager of one cannot leave it without one (409 ``last_ops_manager``)."""
    login = signed_in.login
    record = await _record_or_none(runtime, login)
    client, key = client_key_64(request), login.login_key
    _refuse_if_blocked(
        request,
        [("airline_login", client), ("airline_login_email", key)],
        "too_many_attempts",
        "Too many tries; deleting waits",
    )
    if not await passwords.check_password(body.password, login.password):
        left = _record_failure(request, client, key, "airline_login_email")
        raise _bad_credentials("That password doesn't match", left)
    if _hosted(request):
        refusal = await accounts.deletion_refusal(runtime.store, login, record)
        if refusal is not None:
            raise ApiError(409, refusal, DELETE_REFUSALS[refusal])
    if record is None:
        await _delete_member_login(request, runtime, login)
        logger.info("member login deleted")
    else:
        await accounts.delete_account(runtime.store, record)
        logger.info("airline deleted id=%s", record.id)
    response = Response(status_code=204)
    clear_airline_cookie(response, request)
    return response


@router.post(
    "/airline/feeds/dry-run", response_model=DryRunResult, dependencies=[Depends(require_csrf)]
)
async def dry_run(request: Request, airline: Airline) -> Response:
    """The file checked record by record as a push would be, against the current UTC time.
    Nothing is taken in: pushes from airline accounts never enter the shared picture."""
    _refuse_if_blocked(
        request,
        [("airline_dry_runs", airline.record.id)],
        "too_many_requests",
        "Too many dry runs this hour",
    )
    _throttle(request, "airline_dry_runs").record_failure(airline.record.id)
    raw = await _json_body(request)
    if not isinstance(raw, dict):
        raise ApiError(422, "not_a_push", "file: Input should be an object")
    try:
        result = connections.dry_run(raw, wall_clock_now())
    except connections.NotAPush as exc:
        raise ApiError(422, "not_a_push", str(exc)) from None
    return _json(result)


@router.get("/fleet", response_model=FleetResponse)
async def get_fleet(runtime: RuntimeDep) -> Response:
    """The own-fleet filter this TEPHRA runs with; null when every aircraft is checked."""
    return _json(FleetResponse(own_fleet=runtime.own_fleet()))


async def _delete_member_login(request: Request, runtime: Runtime, login: AirlineLogin) -> None:
    """A member-only login leaves every airline it joined (each one's record says so), then
    goes."""
    from tephra.hosted import members

    registry = request.app.state.registry
    await members.delete_member_login(
        runtime.store,
        login,
        spaces=registry.space,
        access=request.app.state.access,
        at=wall_clock_now(),
    )


# --- the Desk ---------------------------------------------------------------------------

DeskOnboard = [Depends(require_onboard)]
DeskOnboardCsrf = [Depends(require_csrf), Depends(require_onboard)]


async def require_dispatcher(session: DeskSession) -> SessionInfo:
    """An airline's record is private to this site's dispatchers: a visitor is refused here on
    every route (``DISPATCHER_ONLY_PATHS`` names the GET prefix too, but a POST prefix there would
    name a path no route serves)."""
    if session.role == "visitor":
        raise ApiError(403, "visitor_role", VISITOR_ROLE_DETAIL)
    return session


Dispatcher = Annotated[SessionInfo, Depends(require_dispatcher)]


async def _desk_record(runtime: Runtime, airline_id: str) -> AirlineRecord:
    """A submitted airline: a draft is the airline's own, and answers 404 like a missing one."""
    if _AIRLINE_ID.fullmatch(airline_id) is None:
        raise ApiError(404, "not_found", "No such airline")
    try:
        record = await accounts.get_record(runtime.store, airline_id)
    except accounts.AirlineNotFound:
        raise ApiError(404, "not_found", "No such airline") from None
    if record.status == "draft":
        raise ApiError(404, "not_found", "No such airline")
    return record


def _desk_view(record: AirlineRecord) -> AirlineDeskView:
    broken = accounts.verify_history(record.history)
    return AirlineDeskView(
        **AirlineDeskRow.of(record).model_dump(),
        answers=record.submitted(),
        history=record.history,
        history_ok=broken is None,
        history_broken_at=broken,
    )


@router.get("/desk/airlines", response_model=AirlineList, dependencies=DeskOnboard)
async def list_airlines(
    session: Dispatcher,
    runtime: RuntimeDep,
    status: DeskStatus | Literal["all"] = "pending",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Response:
    records = await accounts.list_airlines(runtime.store, status, limit)
    return _json(AirlineList(airlines=[AirlineDeskRow.of(record) for record in records]))


@router.get("/desk/airlines/summary", response_model=PendingSummary, dependencies=DeskOnboard)
async def airlines_summary(session: Dispatcher, runtime: RuntimeDep) -> Response:
    return _json(PendingSummary(pending=await accounts.pending_count(runtime.store)))


@router.get("/desk/airlines/{airline_id}", response_model=AirlineDeskView, dependencies=DeskOnboard)
async def get_airline(airline_id: str, session: Dispatcher, runtime: RuntimeDep) -> Response:
    return _json(_desk_view(await _desk_record(runtime, airline_id)))


async def _decide(
    runtime: Runtime,
    airline_id: str,
    session: SessionInfo,
    *,
    version: int,
    verified: bool,
    note: str | None,
) -> Response:
    await _desk_record(runtime, airline_id)
    try:
        record = await accounts.decide(
            runtime.store,
            airline_id,
            version=version,
            actor=_actor(session),
            verified=verified,
            note=note,
            at=wall_clock_now(),
        )
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.NotPending:
        raise ApiError(
            422, "not_pending", "Only an airline pending verification can be decided"
        ) from None
    return _json(_desk_view(record))


@router.post(
    "/desk/airlines/{airline_id}/verify",
    response_model=AirlineDeskView,
    dependencies=DeskOnboardCsrf,
)
async def verify_airline(
    airline_id: str, body: VerifyAirline, session: Dispatcher, runtime: RuntimeDep
) -> Response:
    """A person checked who this operator is; it approves no policy and publishes nothing."""
    return await _decide(
        runtime, airline_id, session, version=body.version, verified=True, note=body.note
    )


@router.post(
    "/desk/airlines/{airline_id}/decline",
    response_model=AirlineDeskView,
    dependencies=DeskOnboardCsrf,
)
async def decline_airline(
    airline_id: str, body: DeclineAirline, session: Dispatcher, runtime: RuntimeDep
) -> Response:
    return await _decide(
        runtime, airline_id, session, version=body.version, verified=False, note=body.reason
    )


@router.post("/desk/airlines/{airline_id}/delete", status_code=204, dependencies=DeskOnboardCsrf)
async def delete_airline(
    airline_id: str, body: DeleteAirline, session: Dispatcher, runtime: RuntimeDep
) -> Response:
    """A declined airline's record and login, so spam does not fill the 1,000-record cap."""
    await _desk_record(runtime, airline_id)
    try:
        await accounts.desk_delete(runtime.store, airline_id, version=body.version)
    except accounts.VersionConflict:
        raise _version_conflict() from None
    except accounts.NotDeclined:
        raise ApiError(
            422, "not_declined", "Only a declined airline's record can be deleted"
        ) from None
    logger.info("airline deleted by desk id=%s", airline_id)
    return Response(status_code=204)
