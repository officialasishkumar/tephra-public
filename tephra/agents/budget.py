"""The day's model-call budgets and the AI work waiting for them, as the Wall and Desk show
them (``GET /api/budget``, SSE ``budget``). Kept apart from the HTTP routes so the pipeline and
the AI worker can publish it without importing the API.

The counts come from the quota ledger (``tephra.agents.quota``), per model id; the waiting work
comes from the AI worker's queue (``ai_work``). Everything here is written by code in plain
words; nothing a model wrote is shown.
"""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Final, Literal

from pydantic import Field

from tephra.agents.llm import LlmBackend, Tier
from tephra.agents.quota import LANES, Lane, ModelDay, QuotaLedger, Shares, day_bounds
from tephra.config import Settings
from tephra.models import DutyItem, TephraModel, UtcDatetime
from tephra.util import timeutil

__all__ = [
    "AiWork",
    "BudgetLane",
    "BudgetModel",
    "BudgetTier",
    "BudgetView",
    "budget_view",
    "slot_words",
]

QUOTA_NOTE: Final = (
    "Free-tier quotas are counted per model and per day, and reset at midnight Pacific time."
)
TIER_JOBS: Final[dict[Tier, str]] = {
    "main": "Plume Reader",
    "lite": "every other AI step",
    "tts": "spoken answers",
}
"""Joined with "and" for a model that runs several tiers; the first letter is then capitalised."""
LANE_WORDS: Final[dict[Lane, str]] = {
    "urgent": "urgent (flights in or near the area)",
    "interactive": "Desk (questions, voice, notices, messages, documents)",
    "routine": "routine (paced through the day)",
}
WorkStatus = Literal["QUEUED", "WAITING", "RUNNING"]
HOURS_A_DAY: Final = 24


class AiWork(TephraModel):
    """One piece of AI work in the AI worker's queue (``ai_work/<id>``).

    A Duty Officer item (``item``) or a network recovery run (``airports``). WAITING work is
    routine work its model's budget has no slot for yet: it is kept, shown with the time of its
    next slot, and never handed to another model."""

    id: str
    kind: Literal["duty_item", "recover"]
    label: str = Field(description="Code-written, e.g. 'Plan RFA4238 (Semeru): ...'")
    item: DutyItem | None = None
    airports: list[str] = Field(default_factory=list)
    model_id: str
    lane: Lane
    urgency: int = Field(ge=0)
    status: WorkStatus
    since: UtcDatetime = Field(description="Wall clock: when the work was first queued")
    next_slot_at: UtcDatetime | None = None
    reason: str | None = Field(default=None, description="Why it waits, in plain words")
    replay: bool = False


def slot_words(next_slot_at: datetime | None) -> str:
    if next_slot_at is None:
        return "waiting for AI budget"
    return f"waiting for AI budget, next slot {timeutil.hhmmz(next_slot_at)}"


class BudgetLane(TephraModel):
    lane: Lane
    words: str
    used: int
    share: int = Field(description="Calls set aside for this lane today")


class BudgetModel(TephraModel):
    """One model's calls today."""

    model_id: str
    jobs: str = Field(description="What runs on it, in plain words")
    used: int
    limit: int = Field(description="TEPHRA's budget: the free limit less a margin")
    free_limit: int | None = Field(description="Google's free-tier requests a day, if known")
    remaining: int
    closed: bool = Field(description="Google answered 429 for today's quota")
    lanes: list[BudgetLane] = Field(description="Only the lanes this model's jobs use")
    routine_allowed_now: int = Field(description="Routine calls the pacing allows by now")
    next_routine_slot: UtcDatetime | None = Field(
        default=None, description="When routine work fits again, if it is paced now"
    )
    pacing: str = Field(description="The pacing state in plain words")


class BudgetTier(TephraModel):
    """A tier's view of its model's count (two tiers on one model show the same count)."""

    tier: Tier
    model_id: str
    used: int
    limit: int
    remaining: int


class BudgetView(TephraModel):
    """Model calls used today per model, the pacing state, and the AI work waiting for it."""

    backend: str
    as_of: UtcDatetime
    quota_day: date
    resets_at: UtcDatetime = Field(description="Midnight Pacific: every count starts again")
    models: list[BudgetModel]
    tiers: list[BudgetTier]
    waiting: list[AiWork] = Field(default_factory=list)
    note: str = QUOTA_NOTE


async def budget_view(
    settings: Settings, llm: LlmBackend, quota: QuotaLedger, work: Sequence[AiWork] = ()
) -> BudgetView:
    """The day's counts from the ledger (its copy, read from the store once a day). The stub
    backend spends no quota, so its models read zero used."""
    tiers: tuple[Tier, ...] = ("main", "lite", "tts")
    ids = {
        tier: llm.model_id(tier) if llm.name != "stub" else _configured(settings, tier)
        for tier in tiers
    }
    days = {day.model_id: day for day in await quota.load_all(ids.values())}
    if llm.name == "stub":
        days = {
            model: ModelDay(quota_day=day.quota_day, model_id=model) for model, day in days.items()
        }
    today = quota.today()
    resets_at = day_bounds(today)[1]
    models = [
        _model_row(
            settings, quota, days[model], [tier for tier in tiers if ids[tier] == model], resets_at
        )
        for model in dict.fromkeys(ids.values())
    ]
    by_model = {row.model_id: row for row in models}
    return BudgetView(
        backend=llm.name,
        as_of=timeutil.SystemClock().now(),
        quota_day=today,
        resets_at=resets_at,
        models=models,
        tiers=[
            BudgetTier(
                tier=tier,
                model_id="stub" if llm.name == "stub" else ids[tier],
                used=by_model[ids[tier]].used,
                limit=by_model[ids[tier]].limit,
                remaining=by_model[ids[tier]].remaining,
            )
            for tier in tiers
        ],
        waiting=sorted(work, key=lambda item: (item.urgency, item.since, item.id)),
    )


def _configured(settings: Settings, tier: Tier) -> str:
    return {"main": settings.model, "lite": settings.model_lite, "tts": settings.model_tts}[tier]


def _model_row(
    settings: Settings,
    quota: QuotaLedger,
    day: ModelDay,
    tiers: Sequence[Tier],
    resets_at: datetime,
) -> BudgetModel:
    shares = Shares.of(settings, day.model_id)
    limit = settings.model_limits.get(day.model_id)
    allowed = 0
    slot = None
    if shares.routine:
        allowed = min(
            shares.routine + sum(shares.unused(day)),
            int(shares.routine_allowance(day, quota.fraction())),
        )
        admission = quota.admission(day.model_id, "routine")
        slot = admission.next_slot if not admission.ok else None
    jobs = " and ".join(TIER_JOBS[tier] for tier in tiers)
    share = {"urgent": shares.urgent, "interactive": shares.interactive, "routine": shares.routine}
    return BudgetModel(
        model_id=day.model_id,
        jobs=jobs[:1].upper() + jobs[1:],
        used=day.total,
        limit=shares.budget,
        free_limit=limit.rpd if limit is not None else None,
        remaining=max(0, shares.budget - day.total),
        closed=day.closed,
        lanes=[
            BudgetLane(
                lane=lane, words=LANE_WORDS[lane], used=day.lane_used(lane), share=share[lane]
            )
            for lane in LANES
            if share[lane] or day.lane_used(lane)
        ],
        routine_allowed_now=allowed,
        next_routine_slot=slot,
        pacing=_pacing_words(day, shares, allowed, slot, resets_at, quota.unreadable(day.model_id)),
    )


def _pacing_words(
    day: ModelDay,
    shares: Shares,
    allowed: int,
    slot: datetime | None,
    resets_at: datetime,
    unreadable: str | None,
) -> str:
    reset = timeutil.hhmmz(resets_at)
    if unreadable is not None:
        return f"Count unknown: {unreadable}."
    if day.closed:
        return f"Google reported today's quota spent: no calls until {reset}."
    if shares.budget <= 0:
        return "No budget is set for this model: it is not called."
    if day.total >= shares.budget:
        return f"All {shares.budget} calls used: the budget starts again at {reset}."
    if not shares.routine:
        return "No scheduled work runs on this model: every call is kept for the Desk."
    routine = day.lane_used("routine")
    spread = _spread_words(shares.routine)
    if slot is not None:
        return (
            f"Routine work is paced ({spread}): {routine} routine calls used, {allowed} "
            f"allowed by now; {slot_words(slot)}."
        )
    return f"Routine work ({spread}): {routine} calls used, up to {allowed} allowed by now."


def _spread_words(routine: int) -> str:
    """How the routine share is spread through the quota day (about 24 hours), in plain words."""
    if routine >= HOURS_A_DAY:
        return f"{routine} calls a day, about {round(routine / HOURS_A_DAY)} an hour"
    every = HOURS_A_DAY / routine
    gap = f"{round(every)} hours" if every >= 1.5 else f"{round(every * 60)} minutes"
    return f"{routine} calls a day, about one every {gap}"
