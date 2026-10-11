"""What the document drafts read from the runtime.

``tephra.pipeline.Runtime`` satisfies this; tests pass a small stand-in. Read-only
properties keep the protocol from demanding more than the drafts use.
"""

from typing import Any, Protocol

from tephra.agents.llm import LlmBackend
from tephra.config import Settings
from tephra.models import (
    Aircraft,
    ExposedFlight,
    HazardCone,
    OperatorPolicy,
    PolicySummary,
    RunMode,
    Situation,
    SystemState,
    TraceActor,
    TraceEvent,
    TraceStage,
)
from tephra.store.base import Store
from tephra.util.events import EventBus

__all__ = ["DocsRuntime"]


class DocsRuntime(Protocol):
    @property
    def settings(self) -> Settings: ...

    @property
    def store(self) -> Store: ...

    @property
    def bus(self) -> EventBus: ...

    @property
    def llm(self) -> LlmBackend: ...

    @property
    def policy(self) -> OperatorPolicy: ...

    @property
    def policy_summary(self) -> PolicySummary: ...

    @property
    def mode(self) -> RunMode: ...

    @property
    def situations(self) -> dict[str, Situation]: ...

    @property
    def cones(self) -> dict[str, HazardCone]: ...

    @property
    def exposed(self) -> dict[str, ExposedFlight]: ...

    def aircraft(self) -> list[Aircraft]: ...

    async def system_state(self) -> SystemState: ...

    def trace(
        self,
        stage: TraceStage,
        actor: TraceActor,
        message: str,
        *,
        level: Any = ...,
        volcano_id: str | None = ...,
        flight_id: str | None = ...,
        detail: Any = ...,
    ) -> TraceEvent: ...
