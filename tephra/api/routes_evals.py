"""``GET /api/evals``: the committed evaluation scorecards (``docs/evals/*.json``) as the
scripts wrote them. Public and read-only; nothing is computed here.

The folder is read once per process, on the first request, and kept on ``app.state.evals``:
the files are part of the image and change only with a deploy.
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Final

from fastapi import APIRouter, Request
from starlette.responses import Response

from tephra.api import ApiError
from tephra.api.server import _json
from tephra.config import PROJECT_ROOT
from tephra.models import TephraModel

router = APIRouter()

EVALS_DIR: Final = PROJECT_ROOT / "docs" / "evals"

EVAL_FILES: Final[dict[str, str]] = {
    "plume": "plume-scorecard.json",
    "replay_metrics": "replay-metrics.json",
    "call_counts": "call-counts.json",
}
"""Response key -> file: ``scripts/plume_eval.py --score-only``, ``scripts/replay_metrics.py``
and ``scripts/count_model_calls.py``."""

CACHE_CONTROL: Final = "public, max-age=300"


class EvalBundle(TephraModel):
    plume: dict[str, Any] | None = None
    replay_metrics: dict[str, Any] | None = None
    call_counts: dict[str, Any] | None = None

    def is_empty(self) -> bool:
        return self.plume is None and self.replay_metrics is None and self.call_counts is None


def load_evals(folder: Path) -> EvalBundle:
    """Each scorecard that exists, parsed; a missing file is ``None``. A file that is not a
    JSON object raises ``ValueError`` (the route answers 503, never a half-read bundle)."""
    found: dict[str, dict[str, Any]] = {}
    for key, name in EVAL_FILES.items():
        path = folder / name
        if not path.is_file():
            continue
        parsed = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError(f"{name} is not a JSON object")
        found[key] = parsed
    return EvalBundle(**found)


@router.get("/evals", response_model=EvalBundle)
async def get_evals(request: Request) -> Response:
    evals: EvalBundle | None = getattr(request.app.state, "evals", None)
    if evals is None:
        try:
            evals = await asyncio.to_thread(load_evals, EVALS_DIR)
        except (OSError, ValueError):
            raise ApiError(503, "unavailable", "The eval scorecards could not be read") from None
        request.app.state.evals = evals
    if evals.is_empty():
        raise ApiError(
            404, "not_found", "No eval scorecards yet: run scripts/plume_eval.py --score-only"
        )
    return _json(evals, headers={"Cache-Control": CACHE_CONTROL})
