"""Server-Sent Events framing for ``GET /api/events``.

Core publishes every event on the in-process bus; this module only frames them, adds the
idle heartbeat and, when a reconnecting browser sends ``Last-Event-ID``, replays what it
missed from the bus history.
"""

import json
import math
from collections.abc import AsyncGenerator, Callable, Mapping
from typing import Any, Final

from tephra.models import RunMode, SseEvent
from tephra.util import timeutil
from tephra.util.events import Event, EventBus

__all__ = ["RETRY_MS", "event_stream", "format_event", "missed_events", "parse_last_event_id"]

RETRY_MS: Final = 3000
_RESUMABLE: Final = tuple(name.value for name in SseEvent if name is not SseEvent.HEARTBEAT)
_MAX_EVENT_ID_DIGITS: Final = 18


def format_event(event: Event) -> str:
    """``id: {id}\\nevent: {name}\\ndata: {json}\\n\\n``."""
    return _frame(event.name, event.data, event.id)


async def event_stream(
    bus: EventBus,
    *,
    heartbeat_s: float = 15.0,
    last_event_id: int | None = None,
    mode: Callable[[], RunMode] = lambda: RunMode.LIVE,
) -> AsyncGenerator[str, None]:
    """The SSE body: ``retry``, any missed events, then live events and idle heartbeats.

    The subscription is opened before the first chunk is sent so nothing published while
    the browser connects is lost. Starlette cancels this generator when the client goes
    away, and leaving the ``async with`` unsubscribes it.
    """
    async with bus.subscribe() as subscription:
        yield f"retry: {RETRY_MS}\n\n"
        sent = 0
        if last_event_id is not None:
            for event in missed_events(bus, last_event_id):
                sent = event.id
                yield format_event(event)
        while True:
            event = await subscription.get(within_s=heartbeat_s)
            if event is None:
                heartbeat = {"now": timeutil.to_iso(timeutil.now()), "mode": mode().value}
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
