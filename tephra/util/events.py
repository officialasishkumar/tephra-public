"""In-process async event bus feeding the pipeline trace and the SSE stream.

Events live only in this process. That is why the Cloud Run service runs with
``--max-instances=1``: the tick request and every SSE client share one bus.

``publish`` must be called from the event-loop thread (it touches asyncio queues without
locks). A slow subscriber never blocks publishers: when its queue is full the oldest
queued event is dropped and counted.
"""

import asyncio
import itertools
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from tephra.util import timeutil

__all__ = ["Event", "EventBus", "Subscription", "get_bus"]


@dataclass(frozen=True, slots=True)
class Event:
    id: int
    name: str
    data: Any
    at: datetime


class Subscription:
    """One consumer's queue. Use as an async context manager and async iterator."""

    def __init__(self, bus: "EventBus", maxsize: int) -> None:
        self._bus = bus
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    def offer(self, event: Event) -> None:
        if self._queue.full():
            with suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self.dropped += 1
        self._queue.put_nowait(event)

    async def get(self, within_s: float | None = None) -> Event | None:
        """Next event, or ``None`` if ``within_s`` seconds pass first (SSE heartbeats)."""
        try:
            return await asyncio.wait_for(self._queue.get(), within_s)
        except TimeoutError:
            return None

    def close(self) -> None:
        self._bus.unsubscribe(self)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __aiter__(self) -> AsyncIterator[Event]:
        return self

    async def __anext__(self) -> Event:
        return await self._queue.get()


class EventBus:
    """Fan-out of named JSON events with a short per-name history for late joiners."""

    def __init__(self, history_per_event: int = 200) -> None:
        self._subscribers: set[Subscription] = set()
        self._history: dict[str, deque[Event]] = {}
        self._history_size = history_per_event
        self._ids = itertools.count(1)

    def publish(
        self, name: str, data: BaseModel | Mapping[str, Any] | Sequence[Any] | None = None
    ) -> Event:
        """Serialise ``data`` to JSON-safe values and deliver it to every subscriber."""
        payload = data.model_dump(mode="json") if isinstance(data, BaseModel) else data
        event = Event(
            id=next(self._ids),
            name=str(name),
            data=to_jsonable_python(payload),
            at=timeutil.now(),
        )
        self._history.setdefault(event.name, deque(maxlen=self._history_size)).append(event)
        for subscriber in list(self._subscribers):
            subscriber.offer(event)
        return event

    def subscribe(self, maxsize: int = 256) -> Subscription:
        subscription = Subscription(self, maxsize)
        self._subscribers.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        self._subscribers.discard(subscription)

    def recent(self, name: str, limit: int = 50) -> list[Event]:
        """Up to ``limit`` most recent events with this name, oldest first."""
        history = self._history.get(str(name))
        if not history:
            return []
        return list(history)[-limit:]

    def last(self, name: str) -> Event | None:
        history = self._history.get(str(name))
        return history[-1] if history else None

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


_bus = EventBus()


def get_bus() -> EventBus:
    """The process-wide bus used by the pipeline and the SSE endpoint."""
    return _bus
