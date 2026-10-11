"""``GET /api/duty``: the Duty Officer's recent runs, newest first (the Wall's and the Desk's
Duty Officer panels). Public and read-only like the other Wall data."""

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import ValidationError
from starlette.responses import Response

from tephra.api.server import RuntimeDep, _json
from tephra.duty import DUTY_RUN_LIMIT
from tephra.models import DutyRun, RunMode, TephraModel
from tephra.store.base import Collection, Where

router = APIRouter()


class DutyRunList(TephraModel):
    runs: list[DutyRun]


@router.get("/duty", response_model=DutyRunList)
async def get_duty(
    runtime: RuntimeDep, limit: Annotated[int, Query(ge=1, le=DUTY_RUN_LIMIT)] = 10
) -> Response:
    """Runs of the current mode: a replay's runs say nothing about the live desk's flights."""
    docs = await runtime.store.query(
        Collection.DUTY,
        [Where("replay", "==", runtime.mode is RunMode.REPLAY)],
        order_by="started_at",
        descending=True,
        limit=limit,
    )
    runs: list[DutyRun] = []
    for doc in docs:
        try:
            runs.append(DutyRun.model_validate(doc))
        except ValidationError:
            continue  # a run stored by an older build: shown no more, never a 500
    return _json(DutyRunList(runs=runs))
