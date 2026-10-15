"""A model's earlier answer, given again when the same model would be asked materially the
same question.

Each skill names what is material to its question, its *fingerprint*: for the Plume Reader the
official products and the discrepancy set, for the Flight planner the hazard band, the allowed
actions, the urgency and level bands, the open alternates and the usable reroutes, and so on
(each skill's ``*_question``). An answer that passed the code's checks is kept in ``ai_answers``
under a key of the mode (LIVE, or REPLAY and its case), the model id, the skill and that
fingerprint; never the build, so a deploy finds what the last one kept. When the same model is
about to be asked the same material question again within the skill's age limit, the kept
answer is checked again, by the same validators as a fresh one, against the input of the
moment, and used only when it passes. Otherwise the model is asked as usual: its budget and
pacing apply, and when it cannot be asked the step reports AI UNAVAILABLE. A kept answer is
never shown in place of one that failed.

A reused answer keeps the time the model gave it (``answered_at``, on the run's clock, never
later than now) and costs no model call and no budget. Reuse is logged per skill
(``ai_answer`` log lines); nothing in the UI announces it.

A :class:`Reuse` takes the mode, case and picture epoch when the question is put: an answer is
looked up in that scope, and an answer that comes back after a mode switch or a replay loop
is not kept (it would be filed under the new scope). Inside :func:`on_hand_only` (AI work the
AI worker started only because its answers were on hand) a question with no good answer raises
:class:`NotOnHand` instead of letting the skill ask its model; the work then waits for budget.

The age limit is measured on the run's clock (the replay clock in REPLAY, where a loop plays
the same minutes again); the store keeps a LIVE answer for ``ai_answer_keep_h`` of wall-clock
time at most (and no longer than its age limit) and a REPLAY answer for
``ai_answer_replay_keep_h`` (a replay asks the same questions every loop), and
:meth:`AiAnswers.sweep` removes what has expired. A case folder may carry the answers an
earlier run kept (``answers/ai_answers.jsonl``); :meth:`AiAnswers.seed` puts them in the store.
"""

import logging
from collections import Counter, OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta
from typing import Any, Final, Literal, NamedTuple

from pydantic import BaseModel, ValidationError

from tephra.config import Settings
from tephra.models import RunMode, TephraModel, UtcDatetime
from tephra.store.base import Collection, Store
from tephra.util import timeutil
from tephra.util.hashing import sha256_json, sha256_text

__all__ = [
    "AiAnswer",
    "AiAnswers",
    "AnswerScope",
    "NotOnHand",
    "Question",
    "Reuse",
    "Skill",
    "on_hand_only",
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
Outcome = Literal["hit", "miss", "expired", "rejected", "kept", "dropped", "not_on_hand"]

KEY_VERSION: Final = 3
"""Raised when the key recipe or a payload shape changes: older answers are then never found."""
MEMO_SIZE: Final = 2000
"""Answers (and known absences) held in memory, so a recurring question reads the store once."""
SWEEP_PAGE: Final = 50
SWEEP_PAGES: Final = 10
"""At most this many pages a sweep, so a checkpoint never pages through a large backlog"""
SWEEP_EVERY: Final = timedelta(minutes=10)

_ON_HAND_ONLY: ContextVar[bool] = ContextVar("tephra_ai_on_hand_only", default=False)


class NotOnHand(Exception):
    """Work started only because its answers were on hand needs a model after all."""

    def __init__(self, skill: "Skill") -> None:
        super().__init__(f"no good {skill} answer on hand")
        self.skill = skill


@contextmanager
def on_hand_only(enabled: bool = True) -> Iterator[None]:
    """Inside: a question with no good answer raises :class:`NotOnHand`; no model is asked."""
    token = _ON_HAND_ONLY.set(enabled)
    try:
        yield
    finally:
        _ON_HAND_ONLY.reset(token)


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
    epoch: int = 0
    """The picture's epoch (a mode switch or a replay loop starts a new one); not in the key"""


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

    def age(self, now: datetime) -> timedelta:
        """How long ago it was given, on the run's clock (a replay loop may play the minute
        it was given in again, before or after it)."""
        return abs(now - self.answered_at)

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
        self.scope = scope
        """The mode, case and epoch playing now"""
        self._build = settings.build_sha or "local"
        self._keep = timedelta(hours=settings.ai_answer_keep_h)
        self._replay_keep = timedelta(hours=settings.ai_answer_replay_keep_h)
        self._memo: OrderedDict[str, AiAnswer | None] = OrderedDict()
        self._swept_at: datetime | None = None
        self.counts: Counter[tuple[Skill, Outcome]] = Counter()
        """Outcomes per skill since the process started (logged as they happen)"""

    def reuse(self, question: Question) -> "Reuse":
        """The question, put now (in the scope playing now)."""
        return Reuse(self, question)

    async def recall(
        self, question: Question, model_id: str, scope: AnswerScope | None = None
    ) -> AiAnswer | None:
        """The same model's answer to this material question, while it is good; else None. A
        store error is logged and read as none: the model is then asked, as for a new question."""
        scope = scope or self.scope()
        answer = await self._read(self._key(question, model_id, scope))
        if answer is None:
            self._note(question.skill, "miss", scope)
            return None
        if not _good(answer, question):
            self._note(question.skill, "expired", scope)
            return None
        self._note(question.skill, "hit", scope)
        return answer

    async def peek(self, question: Question, model_id: str) -> AiAnswer | None:
        """As :meth:`recall`, for the AI worker's look ahead: nothing is counted or logged."""
        answer = await self._read(self._key(question, model_id, self.scope()))
        return answer if answer is not None and _good(answer, question) else None

    def rejected(
        self, question: Question, problems: list[str], scope: AnswerScope | None = None
    ) -> None:
        """A kept answer failed the checks against the input of the moment: the model is asked."""
        self._note(question.skill, "rejected", scope or self.scope(), "; ".join(problems[:3]))

    async def keep(
        self,
        question: Question,
        model_id: str,
        payload: Mapping[str, Any],
        *,
        prompt_hash: str,
        answered_at: datetime,
        scope: AnswerScope | None = None,
    ) -> None:
        """Keep an answer that passed the code's checks; a newer one replaces it. ``scope`` is
        the one the question was put in: once the picture was reset, the answer is not kept."""
        now = self.scope()
        if scope is not None and scope != now:
            self._note(question.skill, "dropped", scope, "the picture was reset meanwhile")
            return
        key = self._key(question, model_id, now)
        wall = timeutil.SystemClock().now()
        life = self._replay_keep if now.mode is RunMode.REPLAY else self._keep
        if now.mode is RunMode.LIVE and question.max_age is not None:
            life = min(life, question.max_age)
        answer = AiAnswer(
            key=key,
            mode=now.mode,
            case_id=now.case_id,
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
        self._note(question.skill, "kept", now)

    async def sweep(self) -> int:
        """Delete expired answers, oldest expiry first, at most every ten minutes and at most
        :data:`SWEEP_PAGES` pages a time; how many went. Ordered by ``expires_at`` alone, so
        Firestore answers it from its single-field index."""
        wall = timeutil.SystemClock().now()
        if self._swept_at is not None and wall - self._swept_at < SWEEP_EVERY:
            return 0
        self._swept_at = wall
        removed = 0
        for _ in range(SWEEP_PAGES):
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

    def seeded_key(self, doc: Mapping[str, Any]) -> str | None:
        """The key a stored answer has under the recipe in force; None when a field is missing.
        A line written under an older recipe has another key, and is never seeded."""
        try:
            mode, case_id, model_id, skill, fingerprint = (
                doc["mode"],
                doc["case_id"],
                doc["model_id"],
                doc["skill"],
                doc["fingerprint"],
            )
        except KeyError:
            return None
        if not all(isinstance(v, str) for v in (mode, model_id, skill, fingerprint)):
            return None
        if case_id is not None and not isinstance(case_id, str):
            return None
        return _key_of(mode, case_id, model_id, skill, fingerprint)

    async def seed(self, lines: Iterable[Mapping[str, Any]]) -> int:
        """Answers the same model gave to the same material question on an earlier run; every
        recall still goes through recall_as and the skill's validators.

        Only REPLAY answers of the case playing, under the key recipe in force and from a real
        model, go in; an answer already in the store is left alone (it is at least as new).
        Each seeded answer gets a fresh expiry; the times it was given and kept at stay.
        """
        case_id = self.scope().case_id
        wall = timeutil.SystemClock().now()
        seeded = 0
        for doc in lines:
            if doc.get("mode") != RunMode.REPLAY.value or doc.get("case_id") != case_id:
                continue
            key = self.seeded_key(doc)
            if key is None or key != doc.get("key"):
                continue
            if doc.get("model_id") in ("stub", "none") or doc.get("llm_backend") == "stub":
                continue
            try:
                answer = AiAnswer.model_validate({**doc, "expires_at": wall + self._replay_keep})
            except ValueError:
                logger.warning("ignoring an unreadable seed answer %s", key)
                continue
            try:
                if await self._store.get(Collection.AI_ANSWERS, key) is not None:
                    continue
                await self._store.put(Collection.AI_ANSWERS, key, answer.model_dump(mode="json"))
            except Exception as exc:
                logger.warning("seeding a %s answer failed: %s", answer.skill, exc)
                continue
            self._remember(key, answer)
            seeded += 1
        return seeded

    def note_not_on_hand(self, skill: Skill, scope: AnswerScope) -> None:
        self._note(skill, "not_on_hand", scope)

    # --- internals ------------------------------------------------------------------------

    def _key(self, question: Question, model_id: str, scope: AnswerScope) -> str:
        fingerprint = sha256_json(question.material)
        return _key_of(scope.mode.value, scope.case_id, model_id, question.skill, fingerprint)

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

    def _note(self, skill: Skill, outcome: Outcome, scope: AnswerScope, detail: str = "") -> None:
        self.counts[(skill, outcome)] += 1
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


class Reuse:
    """One material question, put now: where a skill looks for, and keeps, its answer. The
    scope (mode, case, epoch) is the one playing when the question was put."""

    def __init__(self, book: AiAnswers, question: Question) -> None:
        self.book = book
        self.question = question
        self.scope = book.scope()

    async def recall(self, model_id: str) -> AiAnswer | None:
        answer = await self.book.recall(self.question, model_id, self.scope)
        if answer is None:
            self._not_on_hand()
        return answer

    async def recall_as[T: BaseModel](
        self, model_id: str, schema: type[T]
    ) -> tuple[AiAnswer, T] | None:
        """:meth:`recall` with the payload read as the skill's answer model; an answer that
        no longer reads (a shape changed under the same key) counts as rejected."""
        answer = await self.recall(model_id)
        if answer is None:
            return None
        try:
            return answer, schema.model_validate(answer.payload)
        except ValidationError as exc:
            self.rejected([f"UNREADABLE KEPT ANSWER ({exc.error_count()} error(s))"])
            return None

    def rejected(self, problems: list[str]) -> None:
        """The kept answer failed the checks now: the skill asks its model (outside
        :func:`on_hand_only`; inside it, :class:`NotOnHand`)."""
        self.book.rejected(self.question, problems, self.scope)
        self._not_on_hand()

    async def keep(
        self,
        model_id: str,
        payload: Mapping[str, Any],
        *,
        prompt_hash: str,
        answered_at: datetime,
    ) -> None:
        await self.book.keep(
            self.question,
            model_id,
            payload,
            prompt_hash=prompt_hash,
            answered_at=answered_at,
            scope=self.scope,
        )

    def _not_on_hand(self) -> None:
        if _ON_HAND_ONLY.get():
            self.book.note_not_on_hand(self.question.skill, self.scope)
            raise NotOnHand(self.question.skill)


def _key_of(mode: str, case_id: str | None, model_id: str, skill: str, fingerprint: str) -> str:
    return sha256_json([KEY_VERSION, mode, case_id, model_id, skill, fingerprint])[:32]


def _good(answer: AiAnswer, question: Question) -> bool:
    """Not past the store's expiry, nor (LIVE, on the run's clock) past the skill's age limit.

    A replay plays the same minutes again: the material question is the situation, so a kept
    REPLAY answer serves the question whenever the loop asks it, before or after the minute
    it was given in. With the age limit, a question asked twice in a loop more than the
    limit apart was asked of the model again in every loop (247 lighter asks per loop on the
    Krakatau window), never settling."""
    if answer.expires_at <= timeutil.SystemClock().now():
        return False
    if answer.mode is RunMode.REPLAY:
        return True
    return question.max_age is None or answer.age(timeutil.now()) <= question.max_age


def _expired(doc: Mapping[str, Any], wall: datetime) -> bool:
    expires = doc.get("expires_at")
    return isinstance(expires, str) and expires <= timeutil.to_iso(wall)
