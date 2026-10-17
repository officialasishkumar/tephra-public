"""What a hosted airline's systems push, as it arrives: per-section counts over the last hour
(:class:`FeedStats`) and per-key counters (:class:`ConnectionStats`), in process memory.

Pushes cost no store read (D23). The feed cards count from when this process began
(``since``), which the Feeds page says; nothing here is persisted. The keys' counters are
written back at most every 10 minutes and when the registry closes.
"""

import re
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Final, Literal

from tephra.airline.models import AirlineAnswers, DryRunResult
from tephra.desk.connections import view as connection_view
from tephra.hosted.models import FeedCard, FeedKeyView, FeedReason, FeedsView, TenantState
from tephra.models import Connection, PushProblem, PushResult
from tephra.store.base import Collection, Store

__all__ = [
    "FLUSH_EVERY",
    "SECTIONS",
    "WINDOW",
    "ConnectionStats",
    "FeedStats",
    "Section",
    "feeds_view",
]

Section = Literal["positions", "flight_plans", "pilot_reports"]
SECTIONS: Final[tuple[Section, ...]] = ("positions", "flight_plans", "pilot_reports")
WINDOW: Final = timedelta(minutes=60)
REASONS_KEPT: Final = 3
FLUSH_EVERY: Final = timedelta(minutes=10)
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z")
_EMPTY_PARENS = re.compile(r"\(\s*\)")


@dataclass(frozen=True, slots=True)
class _Arrival:
    wall_at: datetime
    connection_id: str | None
    """None: a dry run (no key), which never counts as a feed connected"""
    accepted: int
    refused: int
    reasons: tuple[tuple[str, int], ...]
    """(reason in words, how many of this arrival's refusals): every refusal, grouped"""


class FeedStats:
    """Per section, a deque of arrivals covering :data:`WINDOW` (one per push or dry run)."""

    def __init__(self, *, since: datetime) -> None:
        self.since = since
        self._arrivals: dict[Section, deque[_Arrival]] = {name: deque() for name in SECTIONS}

    def record(
        self,
        *,
        accepted: Mapping[Section, int],
        refused: Sequence[PushProblem],
        wall_at: datetime,
        connection_id: str | None,
    ) -> None:
        for section in SECTIONS:
            problems = [p for p in refused if p.section == section]
            taken = accepted.get(section, 0)
            if not taken and not problems:
                continue
            grouped = Counter(_group(p.reason) for p in problems)
            arrivals = self._arrivals[section]
            arrivals.append(
                _Arrival(wall_at, connection_id, taken, len(problems), tuple(grouped.items()))
            )
            self._trim(arrivals, wall_at)

    def record_push(self, result: PushResult, *, wall_at: datetime) -> None:
        self.record(
            accepted={
                "positions": result.accepted,
                "flight_plans": result.plans_taken,
                "pilot_reports": result.reports_taken,
            },
            refused=result.rejected,
            wall_at=wall_at,
            connection_id=result.connection_id,
        )

    def record_dry_run(
        self, result: DryRunResult, *, wall_at: datetime, connection_id: str | None
    ) -> None:
        """A push in setup is checked and counted, never taken in (D10); a dry run of a file
        has no key (``connection_id`` None)."""
        self.record(
            accepted={
                "positions": result.positions.accepted,
                "flight_plans": result.flight_plans.accepted,
                "pilot_reports": result.pilot_reports.accepted,
            },
            refused=result.rejected,
            wall_at=wall_at,
            connection_id=connection_id,
        )

    def last_received(
        self, section: Section, *, now: datetime, keys: Iterable[str] | None = None
    ) -> datetime | None:
        """When the section last arrived through a key (one of ``keys`` when given)."""
        allowed = None if keys is None else set(keys)
        arrivals = self._arrivals[section]
        self._trim(arrivals, now)
        for arrival in reversed(arrivals):
            if arrival.connection_id is None:
                continue
            if allowed is None or arrival.connection_id in allowed:
                return arrival.wall_at
        return None

    def card(
        self, section: Section, *, declared: bool, now: datetime, optional: bool = False
    ) -> FeedCard:
        arrivals = self._arrivals[section]
        self._trim(arrivals, now)
        counts: Counter[str] = Counter()
        for arrival in arrivals:
            for group, n in arrival.reasons:
                counts[group] += n
        return FeedCard(
            feed=section,
            declared=declared,
            last_received_at=next(
                (a.wall_at for a in reversed(arrivals) if a.connection_id is not None), None
            ),
            records_last_hour=sum(a.accepted + a.refused for a in arrivals),
            refused_last_hour=sum(a.refused for a in arrivals),
            reasons=[
                FeedReason(reason=group, count=count)
                for group, count in counts.most_common(REASONS_KEPT)
            ],
            optional=optional,
        )

    @staticmethod
    def _trim(arrivals: deque[_Arrival], now: datetime) -> None:
        while arrivals and now - arrivals[0].wall_at > WINDOW:
            arrivals.popleft()


def _group(reason: str) -> str:
    """A refusal in words, without its record's times: refusals that differ only in their
    times are one reason ("observed_at is not within 5 min of TEPHRA's clock")."""
    words = _EMPTY_PARENS.sub("", _TIME.sub("", reason))
    return " ".join(words.split()) or reason


@dataclass(slots=True)
class _Pending:
    pushes: int = 0
    accepted: int = 0
    rejected: int = 0
    last_push_at: datetime | None = None
    sections: set[str] = field(default_factory=set)


class ConnectionStats:
    """Each key's counters since the last write-back, and the sections it has sent since
    ``since`` (the Feeds page's "Has sent")."""

    def __init__(self, *, since: datetime) -> None:
        self.since = since
        self._pending: dict[str, _Pending] = {}
        self._seen: dict[str, set[str]] = {}
        self._last_push: dict[str, datetime] = {}
        self._flushed_at: datetime | None = None

    def note(
        self,
        connection_id: str,
        *,
        accepted: int,
        rejected: int,
        sections: Iterable[str],
        at: datetime,
    ) -> None:
        pending = self._pending.setdefault(connection_id, _Pending())
        pending.pushes += 1
        pending.accepted += accepted
        pending.rejected += rejected
        pending.last_push_at = at
        names = set(sections)
        pending.sections |= names
        self._seen.setdefault(connection_id, set()).update(names)
        self._last_push[connection_id] = at

    def last_push_at(self, connection: Connection) -> datetime | None:
        """This process's latest push on the key, else the stored one."""
        return self._last_push.get(connection.id, connection.last_push_at)

    def wait_s(self, connection: Connection, *, at: datetime, gap_s: float) -> float | None:
        """Seconds until the key may push again (``hosted_push_gap_s``), or None."""
        last = self.last_push_at(connection)
        if last is None:
            return None
        left = gap_s - (at - last).total_seconds()
        return left if left > 0 else None

    def sections_seen(self, connection_id: str) -> list[str]:
        seen = self._seen.get(connection_id, set())
        return [name for name in SECTIONS if name in seen]

    def merged(self, connection: Connection) -> Connection:
        """The stored connection with what this process has not written back yet."""
        pending = self._pending.get(connection.id)
        if pending is None:
            return connection
        return connection.model_copy(
            update={
                "pushes": connection.pushes + pending.pushes,
                "accepted": connection.accepted + pending.accepted,
                "rejected": connection.rejected + pending.rejected,
                "last_push_at": pending.last_push_at or connection.last_push_at,
            }
        )

    async def flush(self, store: Store, *, at: datetime, force: bool = False) -> int:
        """Write the counters back (one update per key that pushed), at most every
        :data:`FLUSH_EVERY` unless ``force``; returns how many keys were written."""
        if not self._pending:
            return 0
        if not force and self._flushed_at is not None and at - self._flushed_at < FLUSH_EVERY:
            return 0
        written = 0
        for connection_id in list(self._pending):
            delta = self._pending.pop(connection_id)
            try:
                await store.update(Collection.CONNECTIONS, connection_id, _adding(delta))
            except LookupError:
                continue
            except BaseException:
                self._restore(connection_id, delta)
                raise
            written += 1
        self._flushed_at = at
        return written

    def _restore(self, connection_id: str, delta: _Pending) -> None:
        """A write-back that failed keeps its counts for the next one."""
        newer = self._pending.get(connection_id)
        if newer is not None:
            delta.pushes += newer.pushes
            delta.accepted += newer.accepted
            delta.rejected += newer.rejected
            delta.last_push_at = newer.last_push_at or delta.last_push_at
            delta.sections |= newer.sections
        self._pending[connection_id] = delta


def _adding(delta: _Pending) -> Callable[[dict[str, Any] | None], dict[str, Any]]:
    def change(stored: dict[str, Any] | None) -> dict[str, Any]:
        if stored is None:
            raise LookupError("connection gone")
        current = Connection.model_validate(stored)
        return current.model_copy(
            update={
                "pushes": current.pushes + delta.pushes,
                "accepted": current.accepted + delta.accepted,
                "rejected": current.rejected + delta.rejected,
                "last_push_at": delta.last_push_at or current.last_push_at,
            }
        ).model_dump(mode="json")

    return change


def feeds_view(
    *,
    icao: str,
    state: TenantState,
    answers: AirlineAnswers,
    stats: FeedStats,
    conn_stats: ConnectionStats,
    connections: Sequence[Connection],
    now: datetime,
    show_keys: bool,
) -> FeedsView:
    """Feeds: one card per section, and the push keys for ops managers (hints only)."""
    declared = answers.feeds
    cards = [
        stats.card("positions", declared=declared.positions, now=now),
        stats.card("flight_plans", declared=declared.flight_plans, now=now),
        stats.card("pilot_reports", declared=declared.pilot_reports, now=now, optional=True),
    ]
    keys = [
        FeedKeyView(
            **connection_view(conn_stats.merged(connection)).model_dump(),
            sections_seen=conn_stats.sections_seen(connection.id),
        )
        for connection in connections
    ]
    return FeedsView(
        taken_in=state != "setup",
        push_url=f"/a/{icao}/api/push/positions",
        counted_since=stats.since,
        cards=cards,
        keys=keys if show_keys else [],
    )
