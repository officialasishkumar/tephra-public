"""UTC time handling for feed timestamps and the run clock.

Every datetime inside TEPHRA is timezone-aware UTC. Feed formats carry partial dates
("251252" has no month or year), so the parsers that need it take a reference time and
resolve to the candidate nearest to it.

The active clock is process-global so that REPLAY mode can move "now" for every module at
once; library code calls :func:`now` instead of ``datetime.now``.
"""

import math
import re
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

__all__ = [
    "UTC",
    "Clock",
    "FixedClock",
    "ReplayClock",
    "SystemClock",
    "age_s",
    "compact",
    "ddhhmmz",
    "ensure_utc",
    "floor_minutes",
    "get_clock",
    "hhmmz",
    "iso_times",
    "minutes_between",
    "now",
    "now_exact",
    "parse_day_time",
    "parse_ddhhmm",
    "parse_hhmmz",
    "parse_iso",
    "parse_slash_dtg",
    "resolve_day",
    "set_clock",
    "slash_dtg",
    "to_iso",
    "use_clock",
]


def ensure_utc(value: datetime) -> datetime:
    """Return ``value`` converted to UTC; naive datetimes are a programming error."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"naive datetime {value!r}: TEPHRA requires timezone-aware UTC")
    return value.astimezone(UTC)


# --- clocks -----------------------------------------------------------------------------


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    """Wall-clock UTC time (LIVE mode)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A clock that only moves when told to (tests and deterministic scripts)."""

    def __init__(self, at: datetime) -> None:
        self._at = ensure_utc(at)

    def now(self) -> datetime:
        return self._at

    def set(self, at: datetime) -> None:
        self._at = ensure_utc(at)

    def advance(self, delta: timedelta) -> None:
        self._at += delta


class ReplayClock:
    """Recorded time for REPLAY mode.

    Starts at ``begin`` (default ``start``; clamped into the window) when constructed and
    advances at ``speed`` times wall-clock speed. With ``loop`` it wraps back to ``start``
    after ``end`` so a short recording can run all day; without it, time stops at ``end``.

    With ``quantum_s`` the time :meth:`now` reports is floored to that many seconds, and the
    quanta are anchored to the wall clock's own boundaries: a tick fired at :00 plus jitter
    then sees the same replay minute on every loop and every deploy, so a kept answer is
    found again instead of asked again. :meth:`now_exact` keeps the seconds for the display.
    """

    def __init__(
        self,
        start: datetime,
        end: datetime,
        *,
        speed: float = 1.0,
        loop: bool = True,
        begin: datetime | None = None,
        quantum_s: int = 0,
    ) -> None:
        if speed <= 0:
            raise ValueError("replay speed must be positive")
        if quantum_s < 0:
            raise ValueError("replay quantum must be zero or more seconds")
        self.start = ensure_utc(start)
        self.end = ensure_utc(end)
        if self.end < self.start:
            raise ValueError("replay end precedes start")
        self.speed = speed
        self.loop = loop
        self.quantum_s = quantum_s
        first = min(max(ensure_utc(begin), self.start), self.end) if begin else self.start
        self._offset_s = (first - self.start).total_seconds()
        self._t0 = time.monotonic()
        if quantum_s > 0:
            self._t0 -= time.time() % quantum_s

    def now(self) -> datetime:
        elapsed = self._elapsed_s()
        if self.quantum_s > 0:
            elapsed = math.floor(elapsed / self.quantum_s) * self.quantum_s
        return self._at(elapsed)

    def now_exact(self) -> datetime:
        return self._at(self._elapsed_s())

    def _elapsed_s(self) -> float:
        return self._offset_s + (time.monotonic() - self._t0) * self.speed

    def _at(self, elapsed: float) -> datetime:
        span = (self.end - self.start).total_seconds()
        if span <= 0:
            return self.start
        elapsed = elapsed % span if self.loop else min(elapsed, span)
        return self.start + timedelta(seconds=elapsed)


_clock: Clock = SystemClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Temporarily install ``clock`` (tests); restores the previous clock on exit."""
    previous = get_clock()
    set_clock(clock)
    try:
        yield clock
    finally:
        set_clock(previous)


def now() -> datetime:
    """Current time on the active clock (system time in LIVE, recorded time in REPLAY)."""
    return ensure_utc(_clock.now())


def now_exact() -> datetime:
    """The active clock without the replay quantum: the Wall clock and heartbeats keep
    their seconds while ticks see the floored minute."""
    if isinstance(_clock, ReplayClock):
        return ensure_utc(_clock.now_exact())
    return ensure_utc(_clock.now())


# --- parsing ----------------------------------------------------------------------------

_SLASH_DTG = re.compile(r"^\s*(\d{4})(\d{2})(\d{2})\s*/\s*(\d{2})(\d{2})\s*Z?\s*$", re.IGNORECASE)
_DAY_TIME = re.compile(r"^\s*(\d{2})\s*/\s*(\d{2})(\d{2})\s*Z?\s*$", re.IGNORECASE)
_DDHHMM = re.compile(r"^\s*(\d{2})(\d{2})(\d{2})\s*Z?\s*$", re.IGNORECASE)
_HHMM = re.compile(r"^\s*(\d{2})(\d{2})\s*Z?\s*$", re.IGNORECASE)


def parse_slash_dtg(text: str) -> datetime:
    """Parse the VONA/VAA date-time group ``"20260923/2221Z"``."""
    match = _SLASH_DTG.match(text)
    if match is None:
        raise ValueError(f"not a YYYYMMDD/HHMMZ date-time group: {text!r}")
    year, month, day, hour, minute = (int(part) for part in match.groups())
    return _build(year, month, day, hour, minute)


def parse_day_time(text: str, ref: datetime) -> datetime:
    """Parse ``"25/1800Z"`` (VAA forecast steps) to the date nearest ``ref``."""
    match = _DAY_TIME.match(text)
    if match is None:
        raise ValueError(f"not a DD/HHMMZ group: {text!r}")
    day, hour, minute = (int(part) for part in match.groups())
    return resolve_day(day, hour, minute, ref)


def parse_ddhhmm(text: str, ref: datetime) -> datetime:
    """Parse ``"251252"`` or ``"251252Z"`` (SIGMET/TAF DTG) to the date nearest ``ref``."""
    match = _DDHHMM.match(text)
    if match is None:
        raise ValueError(f"not a DDHHMM group: {text!r}")
    day, hour, minute = (int(part) for part in match.groups())
    return resolve_day(day, hour, minute, ref)


def parse_hhmmz(text: str, ref: datetime) -> datetime:
    """Parse ``"1010Z"`` to the instant with that UTC time nearest ``ref`` (within 12 h)."""
    match = _HHMM.match(text)
    if match is None:
        raise ValueError(f"not an HHMMZ group: {text!r}")
    hour, minute = (int(part) for part in match.groups())
    ref = ensure_utc(ref)
    base = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    candidates = [
        base + timedelta(days=offset, hours=hour, minutes=minute) for offset in (-1, 0, 1)
    ]
    return min(candidates, key=lambda candidate: abs((candidate - ref).total_seconds()))


def resolve_day(day: int, hour: int, minute: int, ref: datetime) -> datetime:
    """Resolve a day-of-month time to the month (previous, same, next) nearest ``ref``.

    Hour 24 is accepted (TAF validity "2418/2524") and means 00 on the following day.
    """
    ref = ensure_utc(ref)
    candidates: list[datetime] = []
    for month_offset in (-1, 0, 1):
        year, month = _shift_month(ref.year, ref.month, month_offset)
        try:
            candidates.append(_build(year, month, day, hour, minute))
        except ValueError:
            continue
    if not candidates:
        raise ValueError(f"day {day} does not exist near {ref.isoformat()}")
    return min(candidates, key=lambda candidate: abs((candidate - ref).total_seconds()))


def parse_iso(value: str | int | float | datetime) -> datetime:
    """Parse feed timestamps: ISO 8601 (with ``Z``, offset, or space separator), or epoch.

    Naive values are taken as UTC because every feed TEPHRA reads publishes UTC.
    Epoch numbers above 1e11 are read as milliseconds.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    if isinstance(value, bool):
        raise ValueError("boolean is not a timestamp")
    if isinstance(value, int | float):
        return _from_epoch(float(value))
    text = value.strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return _from_epoch(float(text))
    if "T" not in text and " " in text:
        text = text.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(text)
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


# --- formatting -------------------------------------------------------------------------


def to_iso(value: datetime) -> str:
    """Fixed-width ISO 8601 with milliseconds and ``Z``; sorts lexicographically in time."""
    value = ensure_utc(value)
    return value.strftime("%Y-%m-%dT%H:%M:%S.") + f"{value.microsecond // 1000:03d}Z"


def iso_times(value: Any) -> Any:
    """``value`` with every datetime inside it written by :func:`to_iso`.

    Pydantic writes a raw datetime in an ``Any`` field as '...:00Z' or '...:00.123456Z',
    which does not sort in time; hashes and events always carry the fixed-width form.
    """
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, Mapping):
        return {key: iso_times(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [iso_times(item) for item in value]
    return value


def compact(value: datetime, *, seconds: bool = False) -> str:
    """``20261007T1032Z`` (or ``20261007T103205Z``): used inside ids and file names."""
    return ensure_utc(value).strftime("%Y%m%dT%H%M%SZ" if seconds else "%Y%m%dT%H%MZ")


def hhmmz(value: datetime) -> str:
    return ensure_utc(value).strftime("%H%MZ")


def ddhhmmz(value: datetime) -> str:
    return ensure_utc(value).strftime("%d%H%MZ")


def slash_dtg(value: datetime) -> str:
    """``20260923/2221Z``, the format VONAs and VAAs print."""
    return ensure_utc(value).strftime("%Y%m%d/%H%MZ")


# --- arithmetic -------------------------------------------------------------------------


def minutes_between(start: datetime, end: datetime) -> float:
    """Signed minutes from ``start`` to ``end``."""
    return (ensure_utc(end) - ensure_utc(start)).total_seconds() / 60.0


def age_s(then: datetime, at: datetime | None = None) -> int:
    """Whole seconds elapsed since ``then`` on the active clock (never negative)."""
    reference = now() if at is None else ensure_utc(at)
    return max(0, int((reference - ensure_utc(then)).total_seconds()))


def floor_minutes(value: datetime, minutes: int) -> datetime:
    """Floor to a slot boundary, e.g. the 10-minute Himawari full-disk start time."""
    value = ensure_utc(value).replace(second=0, microsecond=0)
    return value - timedelta(minutes=value.minute % minutes)


# --- internals --------------------------------------------------------------------------


def _build(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    if hour == 24 and minute == 0:
        return datetime(year, month, day, 0, 0, tzinfo=UTC) + timedelta(days=1)
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _shift_month(year: int, month: int, offset: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + offset
    return index // 12, index % 12 + 1


def _from_epoch(seconds: float) -> datetime:
    if seconds > 1e11:
        seconds /= 1000.0
    return datetime.fromtimestamp(seconds, tz=UTC)
