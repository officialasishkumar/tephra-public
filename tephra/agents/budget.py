"""The day's model-call counts, as the Wall and Desk show them (``GET /api/budget``, SSE
``budget``). Kept apart from the HTTP routes so the pipeline can publish it after its own
model calls without importing the API."""

import asyncio
from typing import Final

from tephra.agents.llm import BUDGET_FILE, DailyBudget, LlmBackend, Tier
from tephra.config import Settings
from tephra.models import TephraModel, UtcDatetime
from tephra.util import timeutil

__all__ = ["BudgetTier", "BudgetView", "budget_view"]

QUOTA_NOTE: Final = "Free-tier quotas are per day and reset at midnight Pacific time."


class BudgetTier(TephraModel):
    tier: Tier
    model_id: str
    used: int
    limit: int
    remaining: int


class BudgetView(TephraModel):
    """Model calls used today. The main tier is the Plume Reader's; the lite tier carries
    everything else, speech included."""

    backend: str
    as_of: UtcDatetime
    tiers: list[BudgetTier]
    note: str = QUOTA_NOTE


async def budget_view(settings: Settings, llm: LlmBackend) -> BudgetView:
    """The day's counts, read from the budget file the Gemini backend keeps on every call.

    The stub backend spends no quota, so its tiers read zero used.
    """
    budget = DailyBudget(path=settings.cache_dir / "llm" / BUDGET_FILE)
    limits: dict[Tier, int] = {
        "main": settings.model_daily_budget,
        "lite": settings.model_lite_daily_budget,
    }
    tiers: list[BudgetTier] = []
    for tier, limit in limits.items():
        used = 0 if llm.name == "stub" else await asyncio.to_thread(budget.used, tier)
        tiers.append(
            BudgetTier(
                tier=tier,
                model_id=llm.model_id(tier),
                used=used,
                limit=limit,
                remaining=max(0, limit - used),
            )
        )
    return BudgetView(backend=llm.name, as_of=timeutil.SystemClock().now(), tiers=tiers)
