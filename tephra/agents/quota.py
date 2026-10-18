"""Daily model-call budgets: one per model id and Google quota day, kept in the store.

Google counts the free tier per project and model, and resets the daily count at midnight
Pacific time (research/10). TEPHRA counts the same way: by model id (two tiers on one model
share one count; a per-day 429 closes that model only) and by quota day on the wall clock, even
in REPLAY. The counts live in the store (``ai_budget``, Firestore on Cloud Run), so a new
instance, a crash or a redeploy carries on from the day's count instead of starting at zero.
Every HTTP attempt is reserved here before it is sent, retries included.

Each model's budget is split three ways, by who waits for the work (the *lane*):

* urgent: work a flight or a plume read waits on now. Never paced. It may also take routine's
  share, never the interactive reserve: the loop's urgent work once spent a whole day's calls
  and left the Desk none (live, 18 Oct 2026: urgent 430 of a 135 share, interactive 0 of 90).
  Refused urgent work waits for its next slot, like routine work.
* interactive: work a person at the Desk waits on (Ask, voice, notices, messages, handover,
  documents, a recovery run started from the Desk). It may also take routine's share, never the
  urgent reserve.
* routine: everything else. Admitted only in proportion to the part of the quota day gone by,
  plus a small burst, so a busy morning cannot spend the evening's calls. Late in the day the
  unused urgent and interactive reserves flow to it, and the unused interactive reserve to
  urgent work too.

Pacing decides when a routine job may *start*. Once the AI worker has admitted a job
(``use_lane("routine", admitted=True)``) its calls are counted as routine and are not paced
again, so a run that needs a few more calls than its estimate finishes on the routine share
(later work waits longer for its slot). They are still refused when they would take the urgent
or interactive reserve held at that moment: the run's remaining step reports AI UNAVAILABLE
rather than spend the Desk's calls (the Desk got none of its 90 on 18 Oct 2026).

If the store cannot be read or written, no call goes: the count is unknown, and a guess (a copy
in memory, or zero on a new instance) could spend the day twice. The caller reports AI
UNAVAILABLE, the AI worker keeps routine work waiting, and the store is tried again on the next
call.

A refusal is never a substitute: the caller reports AI UNAVAILABLE, or (the AI worker) keeps
urgent and routine work waiting with the time of its next slot.
"""

import logging
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from typing import Any, Final, Literal, NamedTuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, NonNegativeInt, ValidationError

from tephra.config import Settings
from tephra.models import TephraModel, UtcDatetime
from tephra.store.base import Collection, Store
from tephra.util import timeutil

__all__ = [
    "LANES",
    "Admission",
    "Lane",
    "ModelDay",
    "QuotaLedger",
    "Shares",
    "current_admitted",
    "current_lane",
    "day_bounds",
    "quota_day",
    "use_lane",
]

logger = logging.getLogger(__name__)

Lane = Literal["urgent", "interactive", "routine"]
LANES: Final[tuple[Lane, ...]] = ("urgent", "interactive", "routine")
SEARCH_STEPS: Final = 40
"""Bisection steps for the next routine slot: a day split 2**40 ways is finer than a second."""

_LANE: ContextVar[Lane] = ContextVar("tephra_ai_lane", default="interactive")
_ADMITTED: ContextVar[bool] = ContextVar("tephra_ai_admitted", default=False)


def current_lane() -> Lane:
    """The lane of the model calls made from here: interactive unless the AI worker set one
    (every call outside the worker answers a person at the Desk)."""
    return _LANE.get()


def current_admitted() -> bool:
    """True inside a routine job the AI worker admitted: pacing no longer applies to it."""
    return _ADMITTED.get()


@contextmanager
def use_lane(lane: Lane, *, admitted: bool = False) -> Iterator[None]:
    token = _LANE.set(lane)
    admitted_token = _ADMITTED.set(admitted)
    try:
        yield
    finally:
        _ADMITTED.reset(admitted_token)
        _LANE.reset(token)


def _quota_zone() -> tzinfo:
    try:
        return ZoneInfo("America/Los_Angeles")
    except ZoneInfoNotFoundError:
        # No tz database: Pacific standard time all year (the day starts an hour late in summer).
        return timezone(timedelta(hours=-8))


QUOTA_ZONE: Final = _quota_zone()
"""Free-tier requests per day reset at midnight Pacific time (research/10, rate-limits page)."""


def quota_day(at: datetime) -> date:
    return at.astimezone(QUOTA_ZONE).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """The quota day's start and end in UTC (23 or 25 hours long on a clock change)."""
    start = datetime(day.year, day.month, day.day, tzinfo=QUOTA_ZONE)
    end = start + timedelta(days=1)
    end = datetime(end.year, end.month, end.day, tzinfo=QUOTA_ZONE)
    return start.astimezone(UTC), end.astimezone(UTC)


class ModelDay(TephraModel):
    """One model's calls on one quota day (``ai_budget/<quota day>/<model id>``)."""

    quota_day: date
    model_id: str
    used: dict[Lane, NonNegativeInt] = Field(default_factory=dict)
    closed: bool = Field(default=False, description="Google answered 429 for a per-day quota")
    closed_reason: str | None = None
    updated_at: UtcDatetime | None = None

    @property
    def total(self) -> int:
        return sum(self.used.values())

    def lane_used(self, lane: Lane) -> int:
        return self.used.get(lane, 0)


@dataclass(frozen=True)
class Shares:
    """One model's daily budget in calls, split by lane."""

    budget: int
    urgent: int
    interactive: int
    routine: int
    burst: int
    release_after: float

    @classmethod
    def of(cls, settings: Settings, model_id: str) -> "Shares":
        """A lane no job of this model uses holds nothing: the Plume Reader's model has no
        interactive work, and the speech model has neither urgent nor routine work, so all of
        its calls are Desk calls."""
        budget = settings.daily_budget(model_id)
        worker_models = {settings.model, settings.model_lite}
        interactive_models = {settings.model_lite, settings.model_tts}
        urgent = round(budget * settings.ai_urgent_share) if model_id in worker_models else 0
        if model_id not in worker_models:
            interactive = budget
        elif model_id in interactive_models:
            interactive = round(budget * settings.ai_interactive_share)
        else:
            interactive = 0
        routine = budget - urgent - interactive
        burst = max(1, round(budget * settings.ai_routine_burst)) if routine else 0
        return cls(
            budget=budget,
            urgent=urgent,
            interactive=interactive,
            routine=routine,
            burst=burst,
            release_after=settings.ai_reserve_release,
        )

    def hold(self, fraction: float) -> float:
        """How much of the unused urgent and interactive reserves is still held back."""
        if fraction <= self.release_after or self.release_after >= 1:
            return 1.0
        return max(0.0, (1 - fraction) / (1 - self.release_after))

    def unused(self, day: ModelDay) -> tuple[int, int]:
        return (
            max(0, self.urgent - day.lane_used("urgent")),
            max(0, self.interactive - day.lane_used("interactive")),
        )

    def routine_allowance(self, day: ModelDay, fraction: float) -> float:
        """Routine calls allowed by now: its share times the part of the day gone by, the
        burst, and the reserves released late in the day."""
        released = sum(self.unused(day)) * (1 - self.hold(fraction))
        return self.routine * fraction + self.burst + released


class Admission(NamedTuple):
    ok: bool
    reason: str | None = None
    next_slot: datetime | None = None
    """For urgent and routine work: when it fits again (the next quota day's start if not
    today)"""


def judge(
    day: ModelDay,
    shares: Shares,
    lane: Lane,
    fraction: float,
    calls: int = 1,
    *,
    admitted: bool = False,
) -> Admission:
    """Whether ``calls`` more calls in ``lane`` fit the budget at ``fraction`` of the day.
    ``admitted``: a call inside a routine job already admitted, not paced again but still
    refused when it would take the urgent or interactive reserve held now (a job that needs
    more calls than estimated stops with AI UNAVAILABLE rather than spend the Desk's calls)."""
    model = day.model_id
    if shares.budget <= 0:
        return Admission(
            False, f"{model} has no daily budget (add its limits to TEPHRA_MODEL_LIMITS)"
        )
    if day.closed:
        return Admission(False, f"Google reported today's quota for {model} spent")
    total = day.total
    if total + calls > shares.budget:
        return Admission(False, f"{model} used {total} of {shares.budget} calls today")
    hold = shares.hold(fraction)
    unused_urgent, unused_interactive = shares.unused(day)
    held_interactive = unused_interactive * hold
    if lane == "urgent":
        if total + calls + held_interactive > shares.budget:
            return Admission(False, f"the rest of {model}'s calls today are held for Desk work")
        return Admission(True)
    held_urgent = unused_urgent * hold
    if total + calls + held_urgent > shares.budget:
        return Admission(False, f"the rest of {model}'s calls today are held for urgent work")
    if lane == "interactive":
        return Admission(True)
    held = held_urgent + held_interactive
    if total + calls + held > shares.budget:
        return Admission(
            False, f"the rest of {model}'s calls today are held for urgent and Desk work"
        )
    if admitted:
        return Admission(True)
    allowance = shares.routine_allowance(day, fraction)
    if day.lane_used("routine") + calls > allowance:
        return Admission(
            False,
            f"routine work on {model} is paced: {day.lane_used('routine')} of "
            f"{shares.routine} routine calls used, {int(allowance)} allowed by now",
        )
    return Admission(True)


def next_routine_slot(
    day: ModelDay, shares: Shares, now: datetime, calls: int = 1, *, lane: Lane = "routine"
) -> datetime:
    """The first moment ``calls`` calls in ``lane`` (routine, or urgent waiting for the Desk's
    reserve to be released) fit, assuming no other use until then."""
    start, end = day_bounds(day.quota_day)
    length = (end - start).total_seconds()

    def fits(fraction: float) -> bool:
        return judge(day, shares, lane, fraction, calls).ok

    low = _fraction(now, start, length)
    if fits(low):
        return now
    if not fits(1.0):
        return end
    high = 1.0
    for _ in range(SEARCH_STEPS):
        middle = (low + high) / 2
        if fits(middle):
            high = middle
        else:
            low = middle
    return start + timedelta(seconds=high * length)


def _fraction(at: datetime, start: datetime, length: float) -> float:
    return min(1.0, max(0.0, (at - start).total_seconds() / length))


class _Refused(Exception):
    def __init__(self, admission: Admission) -> None:
        super().__init__(admission.reason)
        self.admission = admission


class QuotaLedger:
    """The day's calls per model: the store holds the count, memory a copy for quick checks.

    ``reserve`` checks the copy, then counts the call in one store transaction that checks
    again against the stored count, so two instances (a rollout) never hand out the same call
    twice. If the store cannot be read or written the call is refused (the count is unknown),
    and the store is tried again on the next call. With no store at all (an offline backtest,
    a test) the count is kept in memory by design.
    """

    def __init__(
        self,
        settings: Settings,
        store: Store | None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._now = now or timeutil.SystemClock().now
        self._days: dict[tuple[date, str], ModelDay] = {}
        self._unreadable: dict[str, str] = {}
        """model id -> why its count cannot be read or written now"""

    def reconfigure(self, settings: Settings) -> None:
        """Budgets and lane shares from ``settings`` from now on (a hosted airline's new
        model, daily limits or Desk reserve). The day's counts are kept: they are per model
        id, in the store, and a call already counted stays counted."""
        self._settings = settings

    def shares(self, model_id: str) -> Shares:
        return Shares.of(self._settings, model_id)

    def today(self) -> date:
        return quota_day(self._now())

    def fraction(self) -> float:
        now = self._now()
        start, end = day_bounds(quota_day(now))
        return _fraction(now, start, (end - start).total_seconds())

    def unreadable(self, model_id: str) -> str | None:
        """Why ``model_id``'s count cannot be read or written now, or None."""
        return self._unreadable.get(model_id)

    async def reserve(self, model_id: str, lane: Lane, *, admitted: bool = False) -> str | None:
        """Count one call to ``model_id`` before it is sent; None when it may go, else why not.
        ``admitted``: the call belongs to a routine job the AI worker admitted."""
        day = await self.load(model_id)
        unreadable = self._unreadable.get(model_id)
        if unreadable is not None:
            return unreadable
        shares = self.shares(model_id)
        fraction = self.fraction()
        checked = judge(day, shares, lane, fraction, admitted=admitted)
        if not checked.ok:
            return checked.reason
        now = self._now()

        def change(stored: dict[str, Any] | None) -> dict[str, Any]:
            current = self._parse(stored, day.quota_day, model_id)
            admission = judge(current, shares, lane, fraction, admitted=admitted)
            if not admission.ok:
                raise _Refused(admission)
            used = {**current.used, lane: current.lane_used(lane) + 1}
            return current.model_copy(update={"used": used, "updated_at": now}).model_dump(
                mode="json"
            )

        if self._store is None:
            self._keep(ModelDay.model_validate(change(day.model_dump(mode="json"))))
            return None
        try:
            stored = await self._store.update(
                Collection.AI_BUDGET, _doc_id(day.quota_day, model_id), change
            )
        except _Refused as refused:
            self._days.pop((day.quota_day, model_id), None)  # another instance counted: reread
            return refused.admission.reason
        except Exception as exc:
            return self._store_failed(model_id, exc)
        self._store_answered(model_id)
        self._keep(ModelDay.model_validate(stored))
        return None

    async def close(self, model_id: str, reason: str) -> None:
        """Google answered 429 for a per-day quota: refuse ``model_id`` until the day ends."""
        day = await self.load(model_id)
        now = self._now()

        def change(stored: dict[str, Any] | None) -> dict[str, Any]:
            current = self._parse(stored, day.quota_day, model_id)
            update = {"closed": True, "closed_reason": reason, "updated_at": now}
            return current.model_copy(update=update).model_dump(mode="json")

        self._keep(ModelDay.model_validate(change(day.model_dump(mode="json"))))
        if self._store is None:
            return
        try:
            stored = await self._store.update(
                Collection.AI_BUDGET, _doc_id(day.quota_day, model_id), change
            )
        except Exception as exc:
            self._store_failed(model_id, exc)
            return
        self._store_answered(model_id)
        self._keep(ModelDay.model_validate(stored))

    async def load(self, model_id: str, *, fresh: bool = False) -> ModelDay:
        """Today's count for ``model_id``: the copy in memory, read from the store once a day
        (or again with ``fresh``, to see another instance's calls, and after a store error).

        When the store cannot be read, ``unreadable(model_id)`` says why and the copy returned
        (the last count read, or none) is for display only: no call is let through on it."""
        today = self.today()
        held = self._days.get((today, model_id))
        if held is not None and not fresh and model_id not in self._unreadable:
            return held
        if self._store is not None:
            try:
                stored = await self._store.get(Collection.AI_BUDGET, _doc_id(today, model_id))
            except Exception as exc:
                self._store_failed(model_id, exc)
                return held or ModelDay(quota_day=today, model_id=model_id)
            self._store_answered(model_id)
            self._keep(self._parse(stored, today, model_id), replace=True)
            return self._days[(today, model_id)]
        if held is None:
            held = ModelDay(quota_day=today, model_id=model_id)
            self._keep(held)
        return held

    async def load_all(self, model_ids: Iterable[str], *, fresh: bool = False) -> list[ModelDay]:
        return [await self.load(model_id, fresh=fresh) for model_id in dict.fromkeys(model_ids)]

    def admission(self, model_id: str, lane: Lane, calls: int = 1) -> Admission:
        """Whether ``calls`` more calls fit now, from the copy in memory (call ``load`` first).
        A refused urgent or routine call carries the time of its next slot (the next quota
        day's start when the model is closed); an interactive call (a person waits now) and a
        count that cannot be read have none."""
        unreadable = self._unreadable.get(model_id)
        if unreadable is not None:
            return Admission(False, unreadable)
        today = self.today()
        day = self._days.get((today, model_id)) or ModelDay(quota_day=today, model_id=model_id)
        shares = self.shares(model_id)
        checked = judge(day, shares, lane, self.fraction(), calls)
        if checked.ok or lane == "interactive":
            return checked
        if day.closed:
            return checked._replace(next_slot=day_bounds(today)[1])
        slot = next_routine_slot(day, shares, self._now(), calls, lane=lane)
        return checked._replace(next_slot=slot)

    def _keep(self, day: ModelDay, *, replace: bool = False) -> None:
        """Counts only grow within a day: an older copy never replaces a newer one."""
        key = (day.quota_day, day.model_id)
        held = self._days.get(key)
        if replace or held is None or day.total >= held.total or day.closed:
            self._days[key] = day
        for old in [k for k in self._days if k[0] != day.quota_day and k[0] < self.today()]:
            del self._days[old]

    @staticmethod
    def _parse(stored: dict[str, Any] | None, day: date, model_id: str) -> ModelDay:
        if stored is not None:
            try:
                parsed = ModelDay.model_validate(stored)
            except ValidationError:
                logger.warning("ignoring an unreadable budget document for %s", model_id)
            else:
                if parsed.quota_day == day and parsed.model_id == model_id:
                    return parsed
        return ModelDay(quota_day=day, model_id=model_id)

    def _store_failed(self, model_id: str, exc: Exception) -> str:
        reason = (
            f"the AI budget store could not be reached ({type(exc).__name__}): "
            f"no call to {model_id} until today's count can be read"
        )
        if model_id not in self._unreadable:
            logger.warning("%s: %s", reason, exc)
        self._unreadable[model_id] = reason
        return reason

    def _store_answered(self, model_id: str) -> None:
        if self._unreadable.pop(model_id, None) is not None:
            logger.info("the AI budget store answers again for %s", model_id)


def _doc_id(day: date, model_id: str) -> str:
    return f"{day.isoformat()}/{model_id}"
