"""Model answers a replay recorded on its first pass, so a loop of the recording does not ask
the model again for the same question.

A replay plays the same recorded feeds again on every loop, so the plume reads, flight plans,
drafts and Duty Officer runs of a loop are the same questions as on the first pass. Each answer
that passed the code's checks is kept in the store (``replay_answers``), keyed by the replay
case, the build, the job (kind and subject), the question it answered (the plume read's input
hash; for the planner, drafter and Duty Officer the hash of the prompt the model was given) and
the model id. A later loop with the same key is given that same answer from the same model,
labelled ``AI answer recorded on this replay's first pass at HHMMZ real time``, and the code's
checks run on it again against the input of the moment. A loop whose question differs at all
(a flight a minute further on, a budget count that moved) asks the model again.

This is not a fallback: nothing is substituted for a failed model call, and an answer is never
used for a different input. LIVE never reads from here; a new build starts a new first pass.
"""

import logging
from datetime import datetime
from typing import Any, Final, Literal

from tephra.models import TephraModel, UtcDatetime
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.hashing import sha256_json

__all__ = ["AnswerKind", "RecordedAnswer", "ReplayAnswers", "recorded_label"]

logger = logging.getLogger(__name__)

AnswerKind = Literal["assess", "plan", "draft", "duty"]
LABEL: Final = "AI answer recorded on this replay's first pass"


def recorded_label(recorded_at: datetime, now: datetime | None = None) -> str:
    """``... first pass at 0912Z real time``, with the day when it was not today (UTC). The
    time is the wall clock's, said so, since it is shown beside the replay clock."""
    now = now or timeutil.SystemClock().now()
    if recorded_at.date() == now.date():
        return f"{LABEL} at {timeutil.hhmmz(recorded_at)} real time"
    return f"{LABEL} on {recorded_at:%d %b} at {timeutil.hhmmz(recorded_at)} real time"


class RecordedAnswer(TephraModel):
    """One answer (``replay_answers/<key>``); ``payload`` is the job's own output model."""

    key: str
    case_id: str
    build: str
    kind: AnswerKind
    subject: str
    input_key: str
    model_id: str
    recorded_at: UtcDatetime
    payload: dict[str, Any]

    @property
    def label(self) -> str:
        return recorded_label(self.recorded_at)


class ReplayAnswers:
    """The first-pass answers of the replay case playing, under this build."""

    def __init__(self, store: Store, *, case_id: str, build: str | None) -> None:
        self._store = store
        self._case_id = case_id
        self._build = build or "local"

    def _key(self, kind: AnswerKind, subject: str, input_key: str, model_id: str) -> str:
        fields = [self._case_id, self._build, kind, subject, input_key, model_id]
        return sha256_json(fields)[:32]

    async def find(
        self, kind: AnswerKind, subject: str, input_key: str, model_id: str
    ) -> RecordedAnswer | None:
        """The recorded answer for exactly this job, input and model, or None. A store error
        is logged and read as none: the model is then asked, as on a first pass."""
        key = self._key(kind, subject, input_key, model_id)
        try:
            doc = await self._store.get(Collection.REPLAY_ANSWERS, key)
        except Exception as exc:
            logger.warning("reading a recorded replay answer failed: %s", exc)
            return None
        if doc is None:
            return None
        try:
            return RecordedAnswer.model_validate(doc)
        except ValueError:
            logger.warning("ignoring an unreadable recorded replay answer %s", key)
            return None

    async def keep(
        self,
        kind: AnswerKind,
        subject: str,
        input_key: str,
        model_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Record an answer that passed the code's checks; the first one recorded stays."""
        key = self._key(kind, subject, input_key, model_id)
        answer = RecordedAnswer(
            key=key,
            case_id=self._case_id,
            build=self._build,
            kind=kind,
            subject=subject,
            input_key=input_key,
            model_id=model_id,
            recorded_at=timeutil.SystemClock().now(),
            payload=payload,
        )

        def first(stored: dict[str, Any] | None) -> dict[str, Any]:
            return stored if stored is not None else answer.model_dump(mode="json")

        try:
            await self._store.update(Collection.REPLAY_ANSWERS, key, first)
        except Exception as exc:
            logger.warning("recording a replay answer failed: %s", exc)
