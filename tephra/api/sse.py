"""Server-Sent Events for ``GET /api/events``.

Core publishes every event on the in-process bus; this module only frames them, adds the
idle heartbeat and, when a reconnecting browser sends ``Last-Event-ID``, replays what it
missed from the bus history. It also counts the open streams, because each one holds a
Cloud Run request slot for as long as its page stays open.
"""

import json
import logging
import math
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping
from typing import Any, Final

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from tephra.models import RunMode, SseEvent
from tephra.util import timeutil
from tephra.util.events import Event, EventBus

__all__ = [
    "RETRY_MS",
    "TENANT_STREAMS_PER_MEMBER",
    "TENANT_STREAM_CHECK_S",
    "TENANT_STREAM_LIFETIME_S",
    "EventStreamResponse",
    "StreamSlots",
    "event_stream",
    "format_event",
    "missed_events",
    "parse_last_event_id",
]

logger = logging.getLogger(__name__)

RETRY_MS: Final = 3000
_RESUMABLE: Final = tuple(
    name.value for name in SseEvent if name not in (SseEvent.HEARTBEAT, SseEvent.END_STREAMS)
)
_MAX_EVENT_ID_DIGITS: Final = 18
TENANT_STREAM_LIFETIME_S: Final = 900.0
"""A hosted airline's stream ends after 15 minutes; the page reopens it, checked again."""
TENANT_STREAM_CHECK_S: Final = 15.0
"""How often a hosted airline's stream asks whether its reader may still read it."""
TENANT_STREAMS_PER_MEMBER: Final = 4
"""Open streams one member may hold in one airline (a map, a Desk and two more tabs), so one
person cannot take every one of the airline's places."""


def format_event(event: Event) -> str:
    """``id: {id}\\nevent: {name}\\ndata: {json}\\n\\n``."""
    return _frame(event.name, event.data, event.id)


async def event_stream(
    bus: EventBus,
    *,
    heartbeat_s: float = 15.0,
    last_event_id: int | None = None,
    mode: Callable[[], RunMode] = lambda: RunMode.LIVE,
    lifetime_s: float | None = None,
    check: Callable[[], Awaitable[bool]] | None = None,
    check_every_s: float = TENANT_STREAM_CHECK_S,
) -> AsyncGenerator[str, None]:
    """The SSE body: ``retry``, any missed events, then live events and idle heartbeats.

    The subscription is opened before the first chunk is sent so nothing published while
    the browser connects is lost. Starlette cancels this generator when the client goes
    away, and leaving the ``async with`` unsubscribes it. A client so slow that its queue
    dropped events is cut off before anything newer is sent: the browser reconnects with
    the last id it received, and :func:`missed_events` replays the gap from the history.
    An ``end_streams`` event on the bus ends the stream too: the runtime sends one when this
    instance is retired by a newer revision, or when ticks stop arriving, so the browser
    reconnects to the instance that is serving.

    A hosted airline's stream also ends after ``lifetime_s`` and as soon as ``check`` (asked
    every ``check_every_s``) answers False: its reader lost the airline.
    """
    started = time.monotonic()
    ends_at = None if lifetime_s is None else started + lifetime_s
    next_check = started + check_every_s
    async with bus.subscribe() as subscription:
        yield f"retry: {RETRY_MS}\n\n"
        sent = 0
        if last_event_id is not None:
            for event in missed_events(bus, last_event_id):
                sent = event.id
                yield format_event(event)
        while True:
            wait_s = heartbeat_s
            if check is not None or ends_at is not None:
                now = time.monotonic()
                if ends_at is not None and now >= ends_at:
                    return
                if check is not None and now >= next_check:
                    if not await check():
                        return
                    next_check = now + check_every_s
                deadlines = [d for d in (ends_at, next_check if check else None) if d is not None]
                wait_s = max(0.0, min(heartbeat_s, *(d - now for d in deadlines)))
            event = await subscription.get(within_s=wait_s)
            if subscription.dropped:
                logger.info("closing a slow event stream: %d events dropped", subscription.dropped)
                return
            if event is not None and event.name == SseEvent.END_STREAMS:
                return
            if event is None:
                heartbeat = {"now": timeutil.to_iso(timeutil.now_exact()), "mode": mode().value}
                yield _frame(SseEvent.HEARTBEAT.value, heartbeat, None)
            elif event.id > sent:
                yield format_event(event)


def missed_events(bus: EventBus, after_id: int) -> list[Event]:
    """Events still in the bus history with an id above ``after_id``, oldest first."""
    events = [
        event for name in _RESUMABLE for event in bus.recent(name, limit=200) if event.id > after_id
    ]
    return sorted(events, key=lambda event: event.id)


def parse_last_event_id(header: str | None) -> int | None:
    if header is None:
        return None
    value = header.strip()
    if not value.isascii() or not value.isdigit() or len(value) > _MAX_EVENT_ID_DIGITS:
        return None
    return int(value)


class StreamSlots:
    """Open event streams, capped so idle pages cannot take every request slot.

    Cloud Run counts an open stream as an in-flight request; at the instance's concurrency
    limit the scheduler's tick and the desk would get no slot at all.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.open = 0

    def acquire(self) -> bool:
        if self.open >= self.limit:
            return False
        self.open += 1
        return True

    def release(self) -> None:
        self.open -= 1


class EventStreamResponse(StreamingResponse):
    """``text/event-stream`` holding one acquired slot, released however the response ends.

    The response, not the generator, cleans up: when the client leaves while a chunk is
    being sent, Starlette cancels the response inside ``send`` and leaves the generator
    paused at its ``yield``, where only the garbage collector would finish it.
    """

    media_type = "text/event-stream"

    def __init__(self, stream: AsyncGenerator[str, None], *slots: StreamSlots) -> None:
        super().__init__(stream, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        self._stream = stream
        self._slots = slots

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            for slots in self._slots:
                slots.release()
            await self._stream.aclose()


def _frame(name: str, data: Any, event_id: int | None) -> str:
    payload = json.dumps(_finite(data), separators=(",", ":"), ensure_ascii=False)
    lines = [f"event: {name}", f"data: {payload}"]
    if event_id is not None:
        lines.insert(0, f"id: {event_id}")
    return "\n".join(lines) + "\n\n"


def _finite(value: Any) -> Any:
    """NaN and infinities become null: ``JSON.parse`` in the browser rejects them."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Mapping):
        return {str(key): _finite(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_finite(item) for item in value]
    return value
