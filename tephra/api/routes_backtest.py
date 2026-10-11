"""``GET /api/backtest``: the latest backtest scorecard (the Wall's Proof panel).

Public and read-only like the other Wall data. The scorecard comes from the store
(collection ``backtest``, document ``latest``) and otherwise from ``docs/backtest/scorecard.json``
as ``scripts/backtest.py`` wrote it. Nothing is computed here.
"""

import asyncio
from typing import Final

from fastapi import APIRouter
from pydantic import ValidationError
from starlette.responses import Response

from tephra.api import ApiError
from tephra.api.server import RuntimeDep, _json
from tephra.backtest.models import BacktestScorecard
from tephra.backtest.runner import LATEST_DOC, load_scorecard
from tephra.config import PROJECT_ROOT
from tephra.store.base import Collection

router = APIRouter()

SCORECARD_PATH: Final = PROJECT_ROOT / "docs" / "backtest" / "scorecard.json"


@router.get("/backtest")
async def get_backtest(runtime: RuntimeDep) -> Response:
    stored = await runtime.store.get(Collection.BACKTEST, LATEST_DOC)
    try:
        if stored is not None:
            return _json(BacktestScorecard.model_validate(stored))
        return _json(await asyncio.to_thread(load_scorecard, SCORECARD_PATH))
    except FileNotFoundError:
        raise ApiError(
            404, "not_found", "No backtest scorecard yet: run scripts/backtest.py"
        ) from None
    except (OSError, ValidationError):
        raise ApiError(503, "unavailable", "The backtest scorecard could not be read") from None
