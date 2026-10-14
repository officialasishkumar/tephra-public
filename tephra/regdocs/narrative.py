"""The four AI-written boxes of an SRA draft, and the checks they must pass.

One lite-tier call (``LlmBackend.structured``: budgeted, cached by input, timed out) writes
the boxes from a facts object. Code then checks them: no clock time, no number or id that is
not in the facts, no safety or approval claim, no claim that ash is gone. One repair is
allowed. A model that gives nothing usable raises :class:`AiUnavailable`: there is no template
text to put in its place.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from tephra.agents.answers import AiAnswers, Question, Reuse, prompt_version
from tephra.agents.llm import LlmBackend, LlmCall, LlmPart
from tephra.agents.validators import clock_problems, first_problems
from tephra.regdocs.models import NarrativeBox, SraNarrative
from tephra.util import timeutil

__all__ = [
    "AI_UNAVAILABLE",
    "BOXES",
    "NARRATIVE_MAX_CHARS",
    "PROMPT_PATH",
    "AiUnavailable",
    "narrative_question",
    "stub_narrative",
    "validate_narrative",
    "write_narrative",
]

PROMPT_PATH: Final = Path(__file__).resolve().parent.parent / "agents" / "prompts" / "sra.md"
AI_UNAVAILABLE: Final = "AI UNAVAILABLE"
BOXES: Final = (
    "information_sources",
    "hazard_summary",
    "exposure_summary",
    "mitigation_summary",
)
NARRATIVE_MAX_CHARS: Final = 600
REPAIR_ECHO_CHARS: Final = 2000
ACRONYMS: Final = frozenset({"VONA", "VAAC", "TAFS"})
"""Four-capital-letter words that are not ICAO location ids."""

_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_FOUR_CAPS = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}(?![A-Za-z0-9])")
_FLIGHT = re.compile(r"(?<![A-Za-z0-9])[A-Z]{3}\d{1,4}[A-Z]?(?![A-Za-z0-9])")
_ID_LIKE = re.compile(
    r"[A-Za-z]{3,8}:[^\s,;)]+|adv_[0-9a-f]{12}|(?:CONE|PA|PLAN|AIF|RR|DOC|D)-[0-9a-f]{6,}"
)
_CLAIMS = re.compile(
    r"\b(?:is|are|remains?|be)\s+(?:safe|acceptable|compliant|approved)\b"
    r"|\bsafe to\b|\bno ash\b|\bash[- ]free\b|\bclear of ash\b"
    r"|\b(?:has|have)\s+(?:cleared|dispersed)\b|\ball clear\b|\bacceptable risk\b",
    re.IGNORECASE,
)


class AiUnavailable(Exception):
    """The model gave no usable boxes. ``str(exc)`` is the line the trace, the stored audit
    entry and the HTTP 503 show."""

    def __init__(self, reason: str, *, model_id: str) -> None:
        super().__init__(f"{AI_UNAVAILABLE}: {reason}")
        self.reason = reason
        self.model_id = model_id


@dataclass(frozen=True)
class _Allowed:
    ids: frozenset[str]
    numbers: frozenset[str]
    words: frozenset[str]

    @classmethod
    def of(cls, facts: Mapping[str, Any]) -> "_Allowed":
        ids = frozenset(str(item) for item in facts.get("allowed_ids", []))
        text = json.dumps(facts, ensure_ascii=False)
        for known in sorted(ids, key=len, reverse=True):
            text = text.replace(known, " ")
        words = frozenset(re.findall(r"[A-Z0-9]+", text.upper()))
        return cls(ids=ids, numbers=frozenset(_numbers(text)), words=words)


def _numbers(text: str) -> set[str]:
    return {_normal(raw.rstrip(",").replace(",", "")) for raw in _NUMBER.findall(text)}


def _normal(token: str) -> str:
    value = float(token)
    return str(int(value)) if value.is_integer() else f"{value:g}"


# --- checks -----------------------------------------------------------------------------


def validate_narrative(narrative: SraNarrative, facts: Mapping[str, Any]) -> list[str]:
    allowed = _Allowed.of(facts)
    problems: list[str] = []
    for name in BOXES:
        problems += _box_problems(name, getattr(narrative, name), allowed)
    return problems


def _box_problems(name: str, box: NarrativeBox, allowed: _Allowed) -> list[str]:
    text = box.text.strip()
    if not text:
        return [f"{name} IS EMPTY"]
    problems = clock_problems(text, name)
    if len(text) > NARRATIVE_MAX_CHARS:
        problems.append(f"{name} IS {len(text)} CHARACTERS; THE LIMIT IS {NARRATIVE_MAX_CHARS}")
    if any(ch != "\n" and not ch.isprintable() for ch in text):
        problems.append(f"{name} HAS CONTROL CHARACTERS")
    invented = sorted(_numbers(text) - allowed.numbers, key=float)
    if invented:
        problems.append(f"{name} HAS NUMBERS NOT IN THE FACTS: {', '.join(invented)}")
    if any(known in text for known in allowed.ids) or _ID_LIKE.search(text):
        problems.append(f"{name} WRITES AN ID IN ITS TEXT; PUT IDS IN source_ids")
    unknown_ids = sorted(set(box.source_ids) - allowed.ids)
    if unknown_ids:
        problems.append(f"{name} source_ids NOT IN allowed_ids: {', '.join(unknown_ids)}")
    problems += _name_problems(name, text, allowed)
    if (claim := _CLAIMS.search(text)) is not None:
        problems.append(f"{name} MAKES A CLAIM THE DRAFT MAY NOT MAKE: {claim.group(0)!r}")
    return problems


def _name_problems(name: str, text: str, allowed: _Allowed) -> list[str]:
    four = {word for word in _FOUR_CAPS.findall(text) if word not in ACRONYMS}
    flights = set(_FLIGHT.findall(text))
    unknown = sorted((four | flights) - allowed.words)
    if not unknown:
        return []
    return [f"{name} NAMES {', '.join(unknown)}: ONLY AIRPORTS AND FLIGHTS IN THE FACTS"]


# --- the call ---------------------------------------------------------------------------


def narrative_question(facts: Mapping[str, Any]) -> Question:
    """SRA boxes are reused only for identical facts (they carry no clock time)."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    return Question("sra", {"prompt": prompt_version(system), "facts": dict(facts)})


async def write_narrative(
    llm: LlmBackend, facts: Mapping[str, Any], *, answers: AiAnswers | None = None
) -> tuple[SraNarrative, LlmCall]:
    """The checked boxes and the call that made them; :class:`AiUnavailable` otherwise. With
    ``answers``, the same model's boxes for identical facts are used when they pass the checks
    now, and new boxes that pass are kept."""
    system = PROMPT_PATH.read_text(encoding="utf-8")
    parts = [LlmPart.of_text(json.dumps(facts, indent=1, ensure_ascii=False))]
    reuse = Reuse(answers, narrative_question(facts)) if answers is not None else None
    if reuse is not None and (held := await _known_narrative(reuse, llm, facts)):
        return held
    narrative, call = await _ask(llm, system, parts, facts)
    problems = _problems(narrative, call, facts)
    answered = narrative is not None or bool(call.raw_text)
    if problems and answered and llm.name != "stub":
        repair = LlmPart.of_text(_repair_text(narrative, call, problems))
        narrative, call = await _ask(llm, system, [*parts, repair], facts)
        problems = _problems(narrative, call, facts)
    if narrative is None or problems:
        reason = (
            f"NO NARRATIVE RETURNED ({call.error or 'unknown error'})"
            if narrative is None
            else f"NARRATIVE FAILED CHECKS AFTER REPAIR: {'; '.join(first_problems(problems, 3))}"
        )
        raise AiUnavailable(reason, model_id=call.model_id)
    if reuse is not None:
        await reuse.keep(
            call.model_id,
            narrative.model_dump(mode="json"),
            prompt_hash=call.prompt_hash,
            answered_at=timeutil.now(),
        )
    return narrative, call


async def _known_narrative(
    reuse: Reuse, llm: LlmBackend, facts: Mapping[str, Any]
) -> tuple[SraNarrative, LlmCall] | None:
    answer = await reuse.recall(llm.model_id("lite"))
    if answer is None:
        return None
    narrative = SraNarrative.model_validate(answer.payload)
    problems = validate_narrative(narrative, facts)
    if problems:
        reuse.rejected(problems)
        return None
    call = LlmCall(backend=llm.name, model_id=answer.model_id, prompt_hash=answer.prompt_hash)
    return narrative, call


async def _ask(
    llm: LlmBackend, system: str, parts: Sequence[LlmPart], facts: Mapping[str, Any]
) -> tuple[SraNarrative | None, LlmCall]:
    return await llm.structured(
        tier="lite",
        system=system,
        parts=parts,
        schema=SraNarrative,
        stub=lambda: stub_narrative(facts),
    )


def _problems(narrative: SraNarrative | None, call: LlmCall, facts: Mapping[str, Any]) -> list[str]:
    if narrative is None:
        return [f"NO NARRATIVE RETURNED ({call.error or 'unknown error'})"]
    return validate_narrative(narrative, facts)


def _repair_text(narrative: SraNarrative | None, call: LlmCall, problems: Sequence[str]) -> str:
    listed = "\n".join(f"- {problem}" for problem in first_problems(problems))
    previous = (
        json.dumps(narrative.model_dump(mode="json"), indent=1)
        if narrative is not None
        else (call.raw_text or "")[:REPAIR_ECHO_CHARS]
    )
    return (
        "Code checks rejected your boxes:\n"
        f"{listed}\n"
        f"Your boxes were:\n{previous}\n"
        "Write all four boxes again, fixing every problem and keeping every other rule."
    )


# --- stub (TEPHRA_LLM=stub; labelled NO MODEL) ------------------------------------------


def stub_narrative(facts: Mapping[str, Any]) -> SraNarrative:
    """Deterministic boxes built from the facts' counts, for offline runs and tests only."""
    counts = facts["counts"]
    ids = list(facts.get("allowed_ids", []))[:2]
    replay = (
        " The picture is a replay of recorded data." if facts.get("run_mode") == "REPLAY" else ""
    )
    return SraNarrative(
        information_sources=NarrativeBox(
            text=(
                f"{counts['conflicts']} conflicts between products were found by code for"
                f" {counts['volcanoes']} volcanoes. The official area stays binding.{replay}"
            ),
            source_ids=ids,
        ),
        hazard_summary=NarrativeBox(
            text=f"The region has {counts['volcanoes']} volcanoes in the current picture.",
            source_ids=ids,
        ),
        exposure_summary=NarrativeBox(
            text=(
                f"{counts['exposed']} flights are exposed and {counts['inside_now']} are"
                " inside the hazard area now."
            ),
            source_ids=ids,
        ),
        mitigation_summary=NarrativeBox(
            text=f"{counts['advisories']} advisories have been drafted for these flights.",
            source_ids=ids,
        ),
    )
