"""A model's earlier answer, given again when the same model would be asked materially the
same question.

Each skill names what is material to its question, its *fingerprint*: for the Plume Reader the
official products and the discrepancy set, for the Flight planner the cone, the allowed actions,
the urgency and level bands and the open alternates, and so on (each skill's ``*_question``).
An answer that passed the code's checks is kept in ``ai_answers`` under a key of the mode (LIVE,
or REPLAY and its case), the build, the model id, the skill and that fingerprint. When the same
model is about to be asked the same material question again within the skill's age limit, the
kept answer is checked again, by the same validators as a fresh one, against the input of the
moment, and used only when it passes. Otherwise the model is asked as usual: its budget and
pacing apply, and when it cannot be asked the step reports AI UNAVAILABLE. A kept answer is
never shown in place of one that failed.

A reused answer keeps the time the model gave it (``answered_at``, on the run's clock, never
later than now) and costs no model call and no budget. Reuse is logged per skill
(``ai_answer`` log lines); nothing in the UI announces it.

The age limit is measured on the run's clock (the replay clock in REPLAY, where a loop plays
the same minutes again); the store keeps an answer for ``ai_answer_keep_h`` of wall-clock time
at most (a LIVE answer only as long as its age limit), and :meth:`AiAnswers.sweep` removes
what has expired.
"""

import logging
from collections import Counter, OrderedDict
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, Final, Literal, NamedTuple

from tephra.config import Settings
from tephra.models import RunMode, TephraModel, UtcDatetime
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, sha256_text

__all__ = [
    "AiAnswer",
    "AiAnswers",
    "AnswerScope",
    "Question",
    "Reuse",
    "Skill",
    "prompt_version",
]

logger = logging.getLogger(__name__)

Skill = Literal[
    "plume_reader",
    "satellite_reader",
    "flight_planner",
    "drafter",
    "coordinator",
    "notice_reader",
    "messages",
    "ask",
    "handover",
    "sra",
]
Outcome = Literal["hit", "miss", "expired", "rejected", "kept"]

KEY_VERSION: Final = 1
"""Raised when the key recipe or a payload shape changes: older answers are then never found."""
MEMO_SIZE: Final = 2000
"""Answers (and known absences) held in memory, so a recurring question reads the store once."""
SWEEP_PAGE: Final = 20
SWEEP_EVERY: Final = timedelta(hours=1)


class Question(NamedTuple):
    """What a skill is about to ask, in its material terms."""

    skill: Skill
    material: Mapping[str, Any]
    """JSON-safe; everything else in the prompt may change without a new question"""
    max_age: timedelta | None = None
    """How long an answer stays good on the run's clock; None: as long as the store keeps it"""


class AnswerScope(NamedTuple):
    mode: RunMode
    case_id: str | None


class AiAnswer(TephraModel):
    """One kept answer (``ai_answers/<key>``); ``payload`` is the skill's own answer model."""

    key: str
    mode: RunMode
    case_id: str | None
    build: str
    skill: Skill
    model_id: str
    fingerprint: str
    answered_at: UtcDatetime
    """When the model gave it, on the run's clock (the replay clock in REPLAY)"""
    stored_at: UtcDatetime
    expires_at: UtcDatetime
    """Wall clock; the store drops the answer after this"""
    prompt_hash: str
    payload: dict[str, Any]

    def shown_at(self, now: datetime) -> datetime:
        """The time to show for it: when it was given, never later than ``now`` (a replay loop
        plays the minute it was given in again)."""
        return min(self.answered_at, now)


def prompt_version(system: str) -> str:
    """A skill's instructions as part of its fingerprint: new instructions, a new question."""
    return sha256_text(system)[:16]


class AiAnswers:
    """The answers kept for the mode playing (``Runtime.answers``)."""

    def __init__(
        self, store: Store, settings: Settings, *, scope: Callable[[], AnswerScope]
    ) -> None:
        self._store = store
        self._scope = scope
        self._build = settings.build_sha or "local"
        self._keep = timedelta(hours=settings.ai_answer_keep_h)
        self._memo: OrderedDict[str, AiAnswer | None] = OrderedDict()
        self._swept_at: datetime | None = None
        self.counts: Counter[tuple[Skill, Outcome]] = Counter()
        """Outcomes per skill since the process started (logged as they happen)"""

    async def recall(self, question: Question, model_id: str) -> AiAnswer | None:
        """The same model's answer to this material question, while it is good; else None. A
        store error is logged and read as none: the model is then asked, as for a new question."""
        answer = await self._read(self._key(question, model_id))
        if answer is None:
            self._note(question.skill, "miss")
            return None
        if not _good(answer, question):
            self._note(question.skill, "expired")
            return None
        self._note(question.skill, "hit")
        return answer

    async def peek(self, question: Question, model_id: str) -> AiAnswer | None:
        """As :meth:`recall`, for the AI worker's look ahead: nothing is counted or logged."""
        answer = await self._read(self._key(question, model_id))
        return answer if answer is not None and _good(answer, question) else None

    def rejected(self, question: Question, problems: list[str]) -> None:
        """A kept answer failed the checks against the input of the moment: the model is asked."""
        self._note(question.skill, "rejected", "; ".join(problems[:3]))

    async def keep(
        self,
        question: Question,
        model_id: str,
        payload: Mapping[str, Any],
        *,
        prompt_hash: str,
        answered_at: datetime,
    ) -> None:
        """Keep an answer that passed the code's checks; a newer one replaces it."""
        key = self._key(question, model_id)
        scope = self._scope()
        wall = timeutil.SystemClock().now()
        life = self._keep
        if scope.mode is RunMode.LIVE and question.max_age is not None:
            life = min(life, question.max_age)
        answer = AiAnswer(
            key=key,
            mode=scope.mode,
            case_id=scope.case_id,
            build=self._build,
            skill=question.skill,
            model_id=model_id,
            fingerprint=sha256_json(question.material),
            answered_at=answered_at,
            stored_at=wall,
            expires_at=wall + life,
            prompt_hash=prompt_hash,
            payload=dict(payload),
        )
        try:
            await self._store.put(Collection.AI_ANSWERS, key, answer.model_dump(mode="json"))
        except Exception as exc:
            logger.warning("keeping a %s answer failed: %s", question.skill, exc)
            return
        self._remember(key, answer)
        self._note(question.skill, "kept")

    async def sweep(self) -> int:
        """Delete expired answers, oldest expiry first, at most once an hour; how many went.
        Ordered by ``expires_at`` alone, so Firestore answers it from its single-field index."""
        wall = timeutil.SystemClock().now()
        if self._swept_at is not None and wall - self._swept_at < SWEEP_EVERY:
            return 0
        self._swept_at = wall
        removed = 0
        while True:
            docs = await self._store.list_docs(
                Collection.AI_ANSWERS, order_by="expires_at", descending=False, limit=SWEEP_PAGE
            )
            expired = [doc for doc in docs if _expired(doc, wall)]
            for doc in expired:
                key = str(doc.get("key"))
                await self._store.delete(Collection.AI_ANSWERS, key)
                self._memo.pop(key, None)
            removed += len(expired)
            if len(expired) < SWEEP_PAGE:
                break
        if removed:
            logger.info("removed %d expired AI answer(s)", removed)
        return removed

    # --- internals ------------------------------------------------------------------------

    def _key(self, question: Question, model_id: str) -> str:
        scope = self._scope()
        fields = [
            KEY_VERSION,
            scope.mode.value,
            scope.case_id,
            self._build,
            model_id,
            question.skill,
            sha256_json(question.material),
        ]
        return sha256_json(fields)[:32]

    async def _read(self, key: str) -> AiAnswer | None:
        if key in self._memo:
            self._memo.move_to_end(key)
            return self._memo[key]
        try:
            doc = await self._store.get(Collection.AI_ANSWERS, key)
        except Exception as exc:
            logger.warning("reading a kept AI answer failed: %s", exc)
            return None
        answer: AiAnswer | None = None
        if doc is not None:
            try:
                answer = AiAnswer.model_validate(doc)
            except ValueError:
                logger.warning("ignoring an unreadable kept AI answer %s", key)
        self._remember(key, answer)
        return answer

    def _remember(self, key: str, answer: AiAnswer | None) -> None:
        self._memo[key] = answer
        self._memo.move_to_end(key)
        while len(self._memo) > MEMO_SIZE:
            self._memo.popitem(last=False)

    def _note(self, skill: Skill, outcome: Outcome, detail: str = "") -> None:
        self.counts[(skill, outcome)] += 1
        scope = self._scope()
        logger.info(
            "ai answer %s skill=%s mode=%s%s",
            outcome,
            skill,
            scope.mode.value,
            f" ({detail})" if detail else "",
            extra={
                "json_fields": {
                    "event": "ai_answer",
                    "skill": skill,
                    "outcome": outcome,
                    "mode": scope.mode.value,
                }
            },
        )


class Reuse(NamedTuple):
    """Where a skill looks for, and keeps, its answer to one material question."""

    book: AiAnswers
    question: Question

    async def recall(self, model_id: str) -> AiAnswer | None:
        return await self.book.recall(self.question, model_id)

    def rejected(self, problems: list[str]) -> None:
        self.book.rejected(self.question, problems)

    async def keep(
        self,
        model_id: str,
        payload: Mapping[str, Any],
        *,
        prompt_hash: str,
        answered_at: datetime,
    ) -> None:
        await self.book.keep(
            self.question, model_id, payload, prompt_hash=prompt_hash, answered_at=answered_at
        )


def _good(answer: AiAnswer, question: Question) -> bool:
    """Not past the store's expiry, nor (on the run's clock) past the skill's age limit."""
    if answer.expires_at <= timeutil.SystemClock().now():
        return False
    age = abs(timeutil.now() - answer.answered_at)
    return question.max_age is None or age <= question.max_age


def _expired(doc: Mapping[str, Any], wall: datetime) -> bool:
    expires = doc.get("expires_at")
    return isinstance(expires, str) and expires <= timeutil.to_iso(wall)
