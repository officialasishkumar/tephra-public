"""``GET /api/duty``: the Duty Officer's recent runs, newest first (the Wall's and the Desk's
Duty Officer panels). Public and read-only like the other Wall data."""

from typing import Annotated, Final

from fastapi import APIRouter, Query
from pydantic import ValidationError
from starlette.responses import Response

from tephra.api.server import RuntimeDep, _json
from tephra.duty import DUTY_RUN_LIMIT
from tephra.models import DutyRun, RunMode, TephraModel
from tephra.store.base import Collection

router = APIRouter()

RUN_WINDOW: Final = 200
"""Newest runs read (by wall-clock storing time), both modes, before the mode filter."""


class DutyRunList(TephraModel):
    runs: list[DutyRun]


@router.get("/duty", response_model=DutyRunList)
async def get_duty(
    runtime: RuntimeDep, limit: Annotated[int, Query(ge=1, le=DUTY_RUN_LIMIT)] = 10
) -> Response:
    """Runs of the current mode: a replay's runs say nothing about the live desk's flights. In
    REPLAY only the run playing counts: each run plays the recording again from its start, so
    an earlier run's Duty Officer runs would sit ahead of the replay clock."""
    docs = await runtime.store.query(
        Collection.DUTY, [], order_by="recorded_wall_at", descending=True, limit=RUN_WINDOW
    )
    replay = runtime.mode is RunMode.REPLAY
    since = runtime.replay_run_since
    runs: list[DutyRun] = []
    for doc in docs:
        try:
            run = DutyRun.model_validate(doc)
        except ValidationError:
            continue  # a run stored by an older build: shown no more, never a 500
        stored = run.recorded_wall_at
        if run.replay != replay or (since is not None and (stored is None or stored < since)):
            continue
        runs.append(run)
        if len(runs) == limit:
            break
    return _json(DutyRunList(runs=runs))
