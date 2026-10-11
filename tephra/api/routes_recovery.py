"""Network recovery routes, mounted under ``/api``.

``GET /recovery`` is public (a fictional airline's plans). Running a plan and deciding it need
a Desk session, and the POSTs need the CSRF header. A run whose model answer failed the checks
is stored as ``AI_UNAVAILABLE`` and answered with HTTP 503; there is no substitute plan.
"""

import asyncio
import re
from collections.abc import Awaitable
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Depends, Response

from tephra.api import ApiError
from tephra.api.auth import require_csrf
from tephra.api.server import DeskSession, Limit, RuntimeDep, _actor, _json
from tephra.models import (
    Airport,
    DecisionRequest,
    Metar,
    RejectRequest,
    RunMode,
    Taf,
    TraceEvent,
)
from tephra.pipeline import Runtime
from tephra.recovery import decisions
from tephra.recovery.agent import recommend_recovery
from tephra.recovery.closures import merge_closures
from tephra.recovery.models import (
    AiUnavailableBody,
    Closure,
    RecoveryPlan,
    RecoveryPlanList,
    RunRequest,
    Schedule,
)
from tephra.recovery.network import network_closures, network_icaos, run_lock
from tephra.recovery.schedule import ScheduleError, load_schedule
from tephra.store.base import Collection
from tephra.util import timeutil
from tephra.util.hashing import SHORT_HASH_LEN

router = APIRouter()

_PLAN_ID: Final = re.compile(rf"^REC-[0-9a-f]{{{SHORT_HASH_LEN}}}$")
MAX_MANUAL_CLOSURE_H: Final = 72


@router.get("/recovery", response_model=RecoveryPlanList)
async def get_recovery(runtime: RuntimeDep, limit: Limit = 20) -> Response:
    """The latest recovery plans in the current mode, newest first."""
    plans = await decisions.list_plans(
        runtime.store, replay=runtime.mode is RunMode.REPLAY, limit=limit
    )
    return _json(RecoveryPlanList(plans=plans))


@router.post(
    "/desk/recovery/run",
    response_model=RecoveryPlan,
    dependencies=[Depends(require_csrf)],
)
async def run_recovery(body: RunRequest, session: DeskSession, runtime: RuntimeDep) -> Response:
    """Plan the network around the airports the hazard closes now, plus any the dispatcher
    entered. One run at a time: it spends the model's daily budget."""
    lock = run_lock(runtime)
    if lock.locked():
        raise ApiError(409, "busy", "A recovery plan is already being made")
    async with lock:
        schedule = await _schedule(runtime)
        closures = await _closures(runtime, schedule, body)
        if not closures:
            raise ApiError(409, "no_closure", "No airport of the RFA network is closed")
        plan = await recommend_recovery(
            schedule,
            closures,
            runtime.llm,
            settings=runtime.settings,
            policy=runtime.policy,
            airports={airport.icao: airport for airport in runtime.airports.all()},
            replay=runtime.mode is RunMode.REPLAY,
            trace=lambda event: _publish(runtime, event),
        )
        await decisions.submit_plan(runtime.store, runtime.bus, plan)
    if plan.status == "AI_UNAVAILABLE":
        unavailable = AiUnavailableBody(message=plan.unavailable_reason or "AI UNAVAILABLE")
        return _json(unavailable, 503)
    return _json(plan)


@router.post(
    "/desk/recovery/{plan_id}/approve",
    response_model=RecoveryPlan,
    dependencies=[Depends(require_csrf)],
)
async def approve_recovery(
    plan_id: str, body: DecisionRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_id(plan_id)
    plan = await _decided(
        decisions.approve(
            runtime.store,
            runtime.bus,
            plan_id,
            expected_version=body.version,
            actor=_actor(session),
        )
    )
    return _json(plan)


@router.post(
    "/desk/recovery/{plan_id}/reject",
    response_model=RecoveryPlan,
    dependencies=[Depends(require_csrf)],
)
async def reject_recovery(
    plan_id: str, body: RejectRequest, session: DeskSession, runtime: RuntimeDep
) -> Response:
    _check_id(plan_id)
    plan = await _decided(
        decisions.reject(
            runtime.store,
            runtime.bus,
            plan_id,
            expected_version=body.version,
            reason=body.reason,
            actor=_actor(session),
        )
    )
    return _json(plan)


# --- helpers ----------------------------------------------------------------------------------


def _check_id(plan_id: str) -> None:
    if _PLAN_ID.fullmatch(plan_id) is None:
        raise ApiError(404, "not_found", "No such recovery plan")


async def _decided(decision: Awaitable[RecoveryPlan]) -> RecoveryPlan:
    try:
        return await decision
    except decisions.PlanNotFound:
        raise ApiError(404, "not_found", "No such recovery plan") from None
    except decisions.VersionConflict:
        raise ApiError(
            409, "version_conflict", "The recovery plan changed since you loaded it"
        ) from None
    except decisions.InvalidTransition as exc:
        raise ApiError(409, "invalid_transition", str(exc)) from None
    except decisions.RejectedInput as exc:
        raise ApiError(
            422, "validation_failed", "Decision rejected", problems=exc.problems
        ) from None


async def _schedule(runtime: Runtime) -> Schedule:
    try:
        return await asyncio.to_thread(load_schedule, runtime.settings.data_dir, timeutil.now())
    except ScheduleError as exc:
        raise ApiError(503, "schedule_unavailable", str(exc)) from None


async def _closures(runtime: Runtime, schedule: Schedule, body: RunRequest) -> list[Closure]:
    network = network_icaos(schedule)
    airports = [airport for airport in runtime.airports.all() if airport.icao in network]
    tafs, metars = await _reports(runtime, airports)
    found = network_closures(runtime, schedule, at=timeutil.now(), tafs=tafs, metars=metars)
    return merge_closures([*found, *_entered(body, network)])


def _entered(body: RunRequest, network: set[str]) -> list[Closure]:
    problems = [
        f"closures.{i}: {closure.icao} is not in the RFA network"
        for i, closure in enumerate(body.closures)
        if closure.icao not in network
    ]
    problems += [
        f"closures.{i}: end must be after start and within {MAX_MANUAL_CLOSURE_H} hours"
        for i, closure in enumerate(body.closures)
        if not timedelta(0) < closure.end - closure.start <= timedelta(hours=MAX_MANUAL_CLOSURE_H)
    ]
    if problems:
        raise ApiError(422, "validation_failed", "Invalid closure", problems=problems)
    return [
        Closure(
            icao=closure.icao,
            start=closure.start,
            end=closure.end,
            reason=f"ENTERED BY DISPATCHER {closure.reference}".strip(),
        )
        for closure in body.closures
    ]


async def _reports(
    runtime: Runtime, airports: list[Airport]
) -> tuple[dict[str, Taf], dict[str, Metar]]:
    tafs: dict[str, Taf] = {}
    metars: dict[str, Metar] = {}
    for airport in airports:
        if doc := await runtime.store.get(Collection.TAFS, airport.icao):
            tafs[airport.icao] = Taf.model_validate(doc)
        if doc := await runtime.store.get(Collection.METARS, airport.icao):
            metars[airport.icao] = Metar.model_validate(doc)
    return tafs, metars


def _publish(runtime: Runtime, event: TraceEvent) -> None:
    runtime.trace(event.stage, event.actor, event.message, level=event.level, detail=event.detail)
